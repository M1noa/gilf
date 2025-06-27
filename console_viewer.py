import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from collections import deque
import threading
from logger import CustomLogger
from shared_memory import SharedMemoryManager, MessageType

class LogLevel(Enum):
    """Log levels for console output"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class ConsoleMessage:
    """Structure for console messages"""
    timestamp: float
    level: LogLevel
    source: str  # 'bot', 'web', 'system'
    message: str
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'timestamp': self.timestamp,
            'level': self.level.value,
            'source': self.source,
            'message': self.message,
            'details': self.details,
            'formatted_time': time.strftime('%H:%M:%S', time.localtime(self.timestamp))
        }

class ConsoleViewer:
    """Manages console output viewing and real-time log streaming"""
    
    def __init__(self, max_messages: int = 1000, max_history_days: int = 7):
        self.max_messages = max_messages
        self.max_history_days = max_history_days
        self.logger = CustomLogger()
        
        # In-memory message buffer
        self.messages: deque[ConsoleMessage] = deque(maxlen=max_messages)
        self.lock = threading.Lock()
        
        # WebSocket connections for real-time updates
        self.websocket_connections: List[Any] = []
        self.connection_lock = threading.Lock()
        
        # Filters
        self.active_filters = {
            'levels': set(LogLevel),
            'sources': {'bot', 'web', 'system'},
            'search_term': '',
            'time_range': None  # (start_time, end_time) or None for all
        }
        
        # Start background tasks
        self._start_log_collector()
        
        self.logger.info("ConsoleViewer initialized")
    
    def _start_log_collector(self):
        """Start background task to collect logs from various sources"""
        def collect_logs():
            while True:
                try:
                    # Collect from shared memory
                    shared_memory = get_shared_memory()
                    messages = shared_memory.receive_messages(max_messages=50)
                    
                    for msg in messages:
                        if msg.message_type in [MessageType.ERROR, MessageType.BOT_STATUS]:
                            level = LogLevel.ERROR if msg.message_type == MessageType.ERROR else LogLevel.INFO
                            self.add_message(
                                level=level,
                                source=msg.sender,
                                message=str(msg.data.get('message', 'Unknown message')),
                                details=msg.data
                            )
                    
                    # Collect from logger files
                    self._collect_from_log_files()
                    
                    time.sleep(1)  # Check every second
                    
                except Exception as e:
                    self.logger.error(f"Error in log collector: {e}")
                    time.sleep(5)  # Wait longer on error
        
        thread = threading.Thread(target=collect_logs, daemon=True)
        thread.start()
    
    def _collect_from_log_files(self):
        """Collect recent logs from log files"""
        try:
            # Get recent logs from the logger
            recent_logs = self.logger.get_recent_logs(limit=10)
            
            for log_entry in recent_logs:
                # Parse log entry and add to console
                if isinstance(log_entry, dict):
                    level_str = log_entry.get('level', 'INFO')
                    try:
                        level = LogLevel(level_str)
                    except ValueError:
                        level = LogLevel.INFO
                    
                    self.add_message(
                        level=level,
                        source='system',
                        message=log_entry.get('message', ''),
                        details=log_entry
                    )
        except Exception as e:
            # Don't log this error to avoid recursion
            pass
    
    def add_message(self, level: LogLevel, source: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Add a new console message"""
        try:
            console_msg = ConsoleMessage(
                timestamp=time.time(),
                level=level,
                source=source,
                message=message,
                details=details
            )
            
            with self.lock:
                self.messages.append(console_msg)
            
            # Broadcast to connected WebSockets
            self._broadcast_message(console_msg)
            
        except Exception as e:
            # Avoid logging errors in the console viewer to prevent recursion
            pass
    
    def get_messages(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get console messages with optional filtering"""
        try:
            with self.lock:
                messages = list(self.messages)
            
            # Apply filters
            if filters:
                messages = self._apply_filters(messages, filters)
            
            # Apply limit
            if limit:
                messages = messages[-limit:]
            
            return [msg.to_dict() for msg in messages]
            
        except Exception as e:
            self.logger.error(f"Error getting messages: {e}")
            return []
    
    def _apply_filters(self, messages: List[ConsoleMessage], filters: Dict[str, Any]) -> List[ConsoleMessage]:
        """Apply filters to message list"""
        filtered = messages
        
        # Level filter
        if 'levels' in filters and filters['levels']:
            level_set = set(LogLevel(level) for level in filters['levels'])
            filtered = [msg for msg in filtered if msg.level in level_set]
        
        # Source filter
        if 'sources' in filters and filters['sources']:
            source_set = set(filters['sources'])
            filtered = [msg for msg in filtered if msg.source in source_set]
        
        # Search term filter
        if 'search_term' in filters and filters['search_term']:
            search_term = filters['search_term'].lower()
            filtered = [msg for msg in filtered if search_term in msg.message.lower()]
        
        # Time range filter
        if 'time_range' in filters and filters['time_range']:
            start_time, end_time = filters['time_range']
            filtered = [msg for msg in filtered if start_time <= msg.timestamp <= end_time]
        
        return filtered
    
    def set_filters(self, filters: Dict[str, Any]):
        """Update active filters"""
        try:
            self.active_filters.update(filters)
            self.logger.debug(f"Updated console filters: {filters}")
        except Exception as e:
            self.logger.error(f"Error setting filters: {e}")
    
    def clear_messages(self):
        """Clear all console messages"""
        try:
            with self.lock:
                self.messages.clear()
            
            # Broadcast clear event
            self._broadcast_event({'type': 'clear'})
            
            self.logger.info("Console messages cleared")
            
        except Exception as e:
            self.logger.error(f"Error clearing messages: {e}")
    
    def export_logs(self, format_type: str = 'json', filters: Optional[Dict[str, Any]] = None) -> str:
        """Export console logs in specified format"""
        try:
            messages = self.get_messages(filters=filters)
            
            if format_type == 'json':
                return json.dumps(messages, indent=2)
            
            elif format_type == 'text':
                lines = []
                for msg in messages:
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg['timestamp']))
                    lines.append(f"[{timestamp}] [{msg['level']}] [{msg['source']}] {msg['message']}")
                return '\n'.join(lines)
            
            elif format_type == 'csv':
                import csv
                import io
                
                output = io.StringIO()
                writer = csv.writer(output)
                
                # Header
                writer.writerow(['timestamp', 'level', 'source', 'message', 'details'])
                
                # Data
                for msg in messages:
                    writer.writerow([
                        msg['timestamp'],
                        msg['level'],
                        msg['source'],
                        msg['message'],
                        json.dumps(msg['details']) if msg['details'] else ''
                    ])
                
                return output.getvalue()
            
            else:
                raise ValueError(f"Unsupported format: {format_type}")
                
        except Exception as e:
            self.logger.error(f"Error exporting logs: {e}")
            return f"Error exporting logs: {e}"
    
    def add_websocket_connection(self, websocket):
        """Add a WebSocket connection for real-time updates"""
        try:
            with self.connection_lock:
                self.websocket_connections.append(websocket)
            
            self.logger.debug(f"Added WebSocket connection. Total: {len(self.websocket_connections)}")
            
        except Exception as e:
            self.logger.error(f"Error adding WebSocket connection: {e}")
    
    def remove_websocket_connection(self, websocket):
        """Remove a WebSocket connection"""
        try:
            with self.connection_lock:
                if websocket in self.websocket_connections:
                    self.websocket_connections.remove(websocket)
            
            self.logger.debug(f"Removed WebSocket connection. Total: {len(self.websocket_connections)}")
            
        except Exception as e:
            self.logger.error(f"Error removing WebSocket connection: {e}")
    
    def _broadcast_message(self, message: ConsoleMessage):
        """Broadcast a new message to all connected WebSockets"""
        if not self.websocket_connections:
            return
        
        try:
            event_data = {
                'type': 'new_message',
                'message': message.to_dict()
            }
            
            self._broadcast_event(event_data)
            
        except Exception as e:
            self.logger.error(f"Error broadcasting message: {e}")
    
    def _broadcast_event(self, event_data: Dict[str, Any]):
        """Broadcast an event to all connected WebSockets"""
        if not self.websocket_connections:
            return
        
        try:
            message = json.dumps(event_data)
            
            # Create a copy of connections to avoid modification during iteration
            with self.connection_lock:
                connections = self.websocket_connections.copy()
            
            # Send to all connections (this should be done in an async context)
            for websocket in connections:
                try:
                    # This is a simplified approach - in practice, you'd want to use asyncio
                    # and handle this properly in an async context
                    if hasattr(websocket, 'send_text'):
                        # For FastAPI WebSocket
                        asyncio.create_task(websocket.send_text(message))
                    elif hasattr(websocket, 'send'):
                        # For other WebSocket implementations
                        asyncio.create_task(websocket.send(message))
                        
                except Exception as e:
                    # Remove broken connections
                    self.remove_websocket_connection(websocket)
                    
        except Exception as e:
            self.logger.error(f"Error broadcasting event: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get console viewer statistics"""
        try:
            with self.lock:
                message_count = len(self.messages)
                
                # Count by level
                level_counts = {level.value: 0 for level in LogLevel}
                for msg in self.messages:
                    level_counts[msg.level.value] += 1
                
                # Count by source
                source_counts = {}
                for msg in self.messages:
                    source_counts[msg.source] = source_counts.get(msg.source, 0) + 1
            
            with self.connection_lock:
                connection_count = len(self.websocket_connections)
            
            return {
                'total_messages': message_count,
                'max_messages': self.max_messages,
                'level_counts': level_counts,
                'source_counts': source_counts,
                'active_connections': connection_count,
                'active_filters': self.active_filters
            }
            
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return {}

# Singleton instance for global access
_console_viewer_instance: Optional[ConsoleViewer] = None

def get_console_viewer() -> ConsoleViewer:
    """Get the global console viewer instance"""
    global _console_viewer_instance
    if _console_viewer_instance is None:
        _console_viewer_instance = ConsoleViewer()
    return _console_viewer_instance

def close_console_viewer():
    """Close the global console viewer instance"""
    global _console_viewer_instance
    if _console_viewer_instance is not None:
        _console_viewer_instance = None