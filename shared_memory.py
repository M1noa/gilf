import mmap
import json
import struct
import threading
import time
import mmap
from typing import Any, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import os
import tempfile
from logger import CustomLogger

class MessageType(Enum):
    """Types of messages that can be sent through shared memory"""
    BOT_STATUS = "bot_status"
    USER_DATA = "user_data"
    COMMAND_RESULT = "command_result"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    WEBSOCKET_MESSAGE = "websocket_message"
    RATE_LIMIT_INFO = "rate_limit_info"
    GUILD_COUNT = "guild_count"
    FRIEND_COUNT = "friend_count"

@dataclass
class SharedMessage:
    """Structure for messages in shared memory"""
    message_type: MessageType
    timestamp: float
    data: Dict[str, Any]
    sender: str  # 'bot' or 'web'
    message_id: str

class SharedMemoryManager:
    """Manages shared memory communication between bot and web processes"""
    
    def __init__(self, memory_size: int = 1024 * 1024, max_messages: int = 100):
        self.memory_size = memory_size
        self.max_messages = max_messages
        self.logger = CustomLogger()
        self.lock = threading.Lock()
        
        # Create temporary file for shared memory
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.write(b'\x00' * memory_size)
        self.temp_file.flush()
        
        # Memory map the file
        self.mmap = mmap.mmap(self.temp_file.fileno(), memory_size)
        
        # Initialize memory structure
        self._initialize_memory()
        
        self.logger.info(f"SharedMemoryManager initialized with {memory_size} bytes")
    
    def _initialize_memory(self):
        """Initialize the shared memory structure"""
        with self.lock:
            # Memory layout:
            # [4 bytes: message_count][4 bytes: read_index][4 bytes: write_index][remaining: message_data]
            self.mmap.seek(0)
            self.mmap.write(struct.pack('III', 0, 0, 0))  # message_count, read_index, write_index
    
    def _get_header_info(self) -> tuple[int, int, int]:
        """Get current header information"""
        self.mmap.seek(0)
        data = self.mmap.read(12)
        return struct.unpack('III', data)
    
    def _update_header(self, message_count: int, read_index: int, write_index: int):
        """Update header information"""
        self.mmap.seek(0)
        self.mmap.write(struct.pack('III', message_count, read_index, write_index))
    
    def send_message(self, message_type: MessageType, data: Dict[str, Any], sender: str) -> bool:
        """Send a message through shared memory"""
        try:
            message = SharedMessage(
                message_type=message_type,
                timestamp=time.time(),
                data=data,
                sender=sender,
                message_id=f"{sender}_{int(time.time() * 1000000)}"
            )
            
            # Serialize message
            message_json = json.dumps({
                'message_type': message.message_type.value,
                'timestamp': message.timestamp,
                'data': message.data,
                'sender': message.sender,
                'message_id': message.message_id
            })
            
            message_bytes = message_json.encode('utf-8')
            message_length = len(message_bytes)
            
            with self.lock:
                message_count, read_index, write_index = self._get_header_info()
                
                # Check if we have space
                available_space = self.memory_size - 12 - write_index
                needed_space = 4 + message_length  # 4 bytes for length + message
                
                if needed_space > available_space:
                    # Compact memory by moving unread messages to the beginning
                    self._compact_memory()
                    message_count, read_index, write_index = self._get_header_info()
                    available_space = self.memory_size - 12 - write_index
                    
                    if needed_space > available_space:
                        self.logger.warning("Shared memory full, dropping oldest message")
                        return False
                
                # Write message
                self.mmap.seek(12 + write_index)
                self.mmap.write(struct.pack('I', message_length))
                self.mmap.write(message_bytes)
                
                # Update header
                new_write_index = write_index + needed_space
                new_message_count = min(message_count + 1, self.max_messages)
                self._update_header(new_message_count, read_index, new_write_index)
                
                self.logger.debug(f"Sent message: {message_type.value} from {sender}")
                return True
                
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False
    
    def receive_messages(self, max_messages: int = 10) -> list[SharedMessage]:
        """Receive messages from shared memory"""
        messages = []
        
        try:
            with self.lock:
                message_count, read_index, write_index = self._get_header_info()
                
                if message_count == 0:
                    return messages
                
                current_pos = read_index
                messages_read = 0
                
                while messages_read < min(max_messages, message_count) and current_pos < write_index:
                    # Read message length
                    self.mmap.seek(12 + current_pos)
                    length_data = self.mmap.read(4)
                    if len(length_data) < 4:
                        break
                    
                    message_length = struct.unpack('I', length_data)[0]
                    
                    # Read message data
                    message_data = self.mmap.read(message_length)
                    if len(message_data) < message_length:
                        break
                    
                    # Parse message
                    try:
                        message_json = json.loads(message_data.decode('utf-8'))
                        message = SharedMessage(
                            message_type=MessageType(message_json['message_type']),
                            timestamp=message_json['timestamp'],
                            data=message_json['data'],
                            sender=message_json['sender'],
                            message_id=message_json['message_id']
                        )
                        messages.append(message)
                        messages_read += 1
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        self.logger.error(f"Error parsing message: {e}")
                    
                    current_pos += 4 + message_length
                
                # Update read position
                new_message_count = message_count - messages_read
                new_read_index = current_pos if new_message_count > 0 else 0
                new_write_index = write_index if new_message_count > 0 else 0
                
                self._update_header(new_message_count, new_read_index, new_write_index)
                
                if messages:
                    self.logger.debug(f"Received {len(messages)} messages")
                
        except Exception as e:
            self.logger.error(f"Error receiving messages: {e}")
        
        return messages
    
    def _compact_memory(self):
        """Compact memory by moving unread messages to the beginning"""
        try:
            message_count, read_index, write_index = self._get_header_info()
            
            if read_index == 0:
                return  # Already compacted
            
            # Read all unread data
            self.mmap.seek(12 + read_index)
            unread_data = self.mmap.read(write_index - read_index)
            
            # Write it to the beginning
            self.mmap.seek(12)
            self.mmap.write(unread_data)
            
            # Update header
            new_write_index = len(unread_data)
            self._update_header(message_count, 0, new_write_index)
            
            self.logger.debug("Compacted shared memory")
            
        except Exception as e:
            self.logger.error(f"Error compacting memory: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get shared memory statistics"""
        try:
            with self.lock:
                message_count, read_index, write_index = self._get_header_info()
                
                return {
                    'total_size': self.memory_size,
                    'used_size': write_index,
                    'available_size': self.memory_size - 12 - write_index,
                    'message_count': message_count,
                    'read_index': read_index,
                    'write_index': write_index,
                    'utilization_percent': (write_index / (self.memory_size - 12)) * 100
                }
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {}
    
    def clear(self):
        """Clear all messages from shared memory"""
        try:
            with self.lock:
                self._initialize_memory()
                self.logger.info("Cleared shared memory")
        except Exception as e:
            self.logger.error(f"Error clearing memory: {e}")
    
    def close(self):
        """Close shared memory and cleanup"""
        try:
            if hasattr(self, 'mmap'):
                self.mmap.close()
            
            if hasattr(self, 'temp_file'):
                self.temp_file.close()
                if os.path.exists(self.temp_file.name):
                    os.unlink(self.temp_file.name)
            
            self.logger.info("SharedMemoryManager closed")
            
        except Exception as e:
            self.logger.error(f"Error closing SharedMemoryManager: {e}")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.close()

# Singleton instance for global access
_shared_memory_instance: Optional[SharedMemoryManager] = None

def get_shared_memory() -> SharedMemoryManager:
    """Get the global shared memory instance"""
    global _shared_memory_instance
    if _shared_memory_instance is None:
        _shared_memory_instance = SharedMemoryManager()
    return _shared_memory_instance

def close_shared_memory():
    """Close the global shared memory instance"""
    global _shared_memory_instance
    if _shared_memory_instance is not None:
        _shared_memory_instance.close()
        _shared_memory_instance = None