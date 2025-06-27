import logging
import logging.handlers
import os
import sys
from datetime import datetime
from typing import Optional
import asyncio
import aiofiles

class CustomLogger:
    def __init__(self, name: str = "DiscordSelfBot", log_dir: str = "data/logs"):
        self.name = name
        self.log_dir = log_dir
        self.logger = None
        self.debug_mode = False
        
        # Ensure log directory exists
        os.makedirs(log_dir, exist_ok=True)
        
        self.setup_logger()
    
    def setup_logger(self, level: str = "INFO"):
        """Setup logger with file and console handlers"""
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # File handler with rotation
        log_file = os.path.join(self.log_dir, f"{self.name.lower()}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        
        # Error file handler
        error_file = os.path.join(self.log_dir, f"{self.name.lower()}_errors.log")
        error_handler = logging.handlers.RotatingFileHandler(
            error_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        
        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.addHandler(error_handler)
        
        # Log startup
        self.logger.info(f"Logger initialized for {self.name}")
    
    def set_debug_mode(self, enabled: bool):
        """Enable/disable debug mode"""
        self.debug_mode = enabled
        
        if enabled:
            self.logger.setLevel(logging.DEBUG)
            # Update console handler to show debug messages
            for handler in self.logger.handlers:
                if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                    handler.setLevel(logging.DEBUG)
            self.logger.debug("Debug mode enabled")
        else:
            self.logger.setLevel(logging.INFO)
            # Reset console handler to INFO level
            for handler in self.logger.handlers:
                if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                    handler.setLevel(logging.INFO)
            self.logger.info("Debug mode disabled")
    
    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error message"""
        self.logger.error(message, exc_info=exc_info, **kwargs)
    
    def critical(self, message: str, exc_info: bool = True, **kwargs):
        """Log critical message"""
        self.logger.critical(message, exc_info=exc_info, **kwargs)
    
    def exception(self, message: str, **kwargs):
        """Log exception with traceback"""
        self.logger.exception(message, **kwargs)
    
    async def log_discord_event(self, event_type: str, data: dict):
        """Log Discord events to separate file"""
        event_file = os.path.join(self.log_dir, "discord_events.log")
        
        try:
            timestamp = datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "event_type": event_type,
                "data": data
            }
            
            async with aiofiles.open(event_file, 'a', encoding='utf-8') as f:
                await f.write(f"{timestamp} | {event_type} | {data}\n")
                
        except Exception as e:
            self.logger.error(f"Failed to log Discord event: {e}")
    
    async def log_websocket_event(self, event_type: str, message: str):
        """Log WebSocket events"""
        ws_file = os.path.join(self.log_dir, "websocket.log")
        
        try:
            timestamp = datetime.now().isoformat()
            
            async with aiofiles.open(ws_file, 'a', encoding='utf-8') as f:
                await f.write(f"{timestamp} | {event_type} | {message}\n")
                
        except Exception as e:
            self.logger.error(f"Failed to log WebSocket event: {e}")
    
    def log_token_operation(self, operation: str, token_name: str, success: bool):
        """Log token operations (without exposing actual tokens)"""
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"Token operation: {operation} for '{token_name}' - {status}")
    
    def log_rate_limit(self, endpoint: str, retry_after: float):
        """Log rate limit events"""
        self.logger.warning(f"Rate limited on {endpoint}, retry after {retry_after}s")
    
    def log_connection_status(self, status: str, details: str = ""):
        """Log connection status changes"""
        message = f"Connection status: {status}"
        if details:
            message += f" - {details}"
        
        if status.lower() in ['connected', 'ready']:
            self.logger.info(message)
        elif status.lower() in ['disconnected', 'reconnecting']:
            self.logger.warning(message)
        else:
            self.logger.error(message)
    
    async def get_recent_logs(self, lines: int = 100, log_type: str = "main") -> list:
        """Get recent log entries"""
        log_files = {
            "main": f"{self.name.lower()}.log",
            "errors": f"{self.name.lower()}_errors.log",
            "discord": "discord_events.log",
            "websocket": "websocket.log"
        }
        
        if log_type not in log_files:
            return []
        
        log_file = os.path.join(self.log_dir, log_files[log_type])
        
        if not os.path.exists(log_file):
            return []
        
        try:
            async with aiofiles.open(log_file, 'r', encoding='utf-8') as f:
                all_lines = await f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            self.logger.error(f"Failed to read log file: {e}")
            return []
    
    def cleanup_old_logs(self, days: int = 30):
        """Clean up log files older than specified days"""
        try:
            import time
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 60 * 60)
            
            for filename in os.listdir(self.log_dir):
                file_path = os.path.join(self.log_dir, filename)
                
                if os.path.isfile(file_path):
                    file_time = os.path.getmtime(file_path)
                    
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        self.logger.info(f"Removed old log file: {filename}")
                        
        except Exception as e:
            self.logger.error(f"Failed to cleanup old logs: {e}")
    
    def get_logger(self) -> logging.Logger:
        """Get the underlying logger instance"""
        return self.logger

# Global logger instance
_global_logger: Optional[CustomLogger] = None

def get_logger(name: str = "DiscordSelfBot") -> CustomLogger:
    """Get or create global logger instance"""
    global _global_logger
    
    if _global_logger is None:
        _global_logger = CustomLogger(name)
    
    return _global_logger

def setup_logging(debug: bool = False, log_level: str = "INFO"):
    """Setup global logging configuration"""
    logger = get_logger()
    logger.setup_logger(log_level)
    
    if debug:
        logger.set_debug_mode(True)
    
    return logger