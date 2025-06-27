import asyncio
import uuid
import time
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from json_manager import JSONManager
from logger import get_logger

@dataclass
class Session:
    session_id: str
    user_id: Optional[str] = None
    token_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    websocket_connections: Set[Any] = field(default_factory=set)
    is_authenticated: bool = False
    discord_ready: bool = False
    
    def to_dict(self) -> dict:
        """Convert session to dictionary for JSON storage"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "token_name": self.token_name,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "data": self.data,
            "is_authenticated": self.is_authenticated,
            "discord_ready": self.discord_ready
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Session':
        """Create session from dictionary"""
        session = cls(
            session_id=data["session_id"],
            user_id=data.get("user_id"),
            token_name=data.get("token_name"),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity=datetime.fromisoformat(data["last_activity"]),
            data=data.get("data", {}),
            is_authenticated=data.get("is_authenticated", False),
            discord_ready=data.get("discord_ready", False)
        )
        return session
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.now()
    
    def is_expired(self, timeout_hours: int = 24) -> bool:
        """Check if session is expired"""
        expiry_time = self.last_activity + timedelta(hours=timeout_hours)
        return datetime.now() > expiry_time
    
    def add_websocket(self, websocket):
        """Add WebSocket connection to session"""
        self.websocket_connections.add(websocket)
        self.update_activity()
    
    def remove_websocket(self, websocket):
        """Remove WebSocket connection from session"""
        self.websocket_connections.discard(websocket)
    
    async def broadcast_to_websockets(self, message: dict):
        """Send message to all WebSocket connections in this session"""
        if not self.websocket_connections:
            return
        
        # Create a copy to avoid modification during iteration
        connections = self.websocket_connections.copy()
        
        for websocket in connections:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                # Remove dead connections
                self.websocket_connections.discard(websocket)

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.json_manager = JSONManager()
        self.logger = get_logger()
        self.cleanup_task = None
        
        # Cleanup task will be started when needed
    
    def _start_cleanup_task(self):
        """Start the background cleanup task"""
        if self.cleanup_task is not None:
            return  # Task already running
            
        async def cleanup_loop():
            while True:
                try:
                    await self.cleanup_expired_sessions()
                    await asyncio.sleep(300)  # Clean up every 5 minutes
                except Exception as e:
                    self.logger.error(f"Error in cleanup task: {e}")
                    await asyncio.sleep(60)  # Retry after 1 minute on error
        
        try:
            self.cleanup_task = asyncio.create_task(cleanup_loop())
        except RuntimeError:
            # No event loop running, task will be started later
            pass
    
    async def create_session(self, user_id: Optional[str] = None, expires_in: int = 3600) -> str:
        """Create a new session"""
        # Start cleanup task if not already running
        if self.cleanup_task is None:
            self._start_cleanup_task()
            
        session_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=datetime.now(),
            expires_at=expires_at,
            websockets=set(),
            data={}
        )
        
        self.sessions[session_id] = session
        await self._save_session(session)
        
        self.logger.info(f"Created new session: {session_id}")
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            session.update_activity()
            await self._save_session(session)
            return session
        
        # Try to load from storage
        session = await self._load_session(session_id)
        if session and not session.is_expired():
            self.sessions[session_id] = session
            session.update_activity()
            await self._save_session(session)
            return session
        
        return None
    
    async def authenticate_session(self, session_id: str, token_name: str, user_id: str) -> bool:
        """Authenticate a session with Discord user info"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.is_authenticated = True
        session.user_id = user_id
        session.token_name = token_name
        session.update_activity()
        
        await self._save_session(session)
        self.logger.info(f"Authenticated session {session_id} for user {user_id}")
        return True
    
    async def set_discord_ready(self, session_id: str, ready: bool = True) -> bool:
        """Mark session as Discord ready"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.discord_ready = ready
        session.update_activity()
        
        await self._save_session(session)
        self.logger.info(f"Set Discord ready status for session {session_id}: {ready}")
        return True
    
    async def update_session_data(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Update session data"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.data.update(data)
        session.update_activity()
        
        await self._save_session(session)
        return True
    
    async def get_session_data(self, session_id: str, key: str = None) -> Any:
        """Get session data"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        if key:
            return session.data.get(key)
        return session.data
    
    async def add_websocket_to_session(self, session_id: str, websocket) -> bool:
        """Add WebSocket connection to session"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.add_websocket(websocket)
        await self._save_session(session)
        return True
    
    async def remove_websocket_from_session(self, session_id: str, websocket) -> bool:
        """Remove WebSocket connection from session"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.remove_websocket(websocket)
        await self._save_session(session)
        return True
    
    async def broadcast_to_session(self, session_id: str, message: dict) -> bool:
        """Broadcast message to all WebSocket connections in session"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        await session.broadcast_to_websockets(message)
        return True
    
    async def destroy_session(self, session_id: str) -> bool:
        """Destroy a session"""
        if session_id in self.sessions:
            session = self.sessions[session_id]
            
            # Close all WebSocket connections
            for websocket in session.websocket_connections.copy():
                try:
                    await websocket.close()
                except Exception:
                    pass
            
            del self.sessions[session_id]
        
        # Remove from storage
        await self._delete_session(session_id)
        
        self.logger.info(f"Destroyed session: {session_id}")
        return True
    
    async def cleanup_expired_sessions(self, timeout_hours: int = 24):
        """Clean up expired sessions"""
        expired_sessions = []
        
        for session_id, session in self.sessions.items():
            if session.is_expired(timeout_hours):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.destroy_session(session_id)
        
        if expired_sessions:
            self.logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    async def get_active_sessions(self) -> Dict[str, dict]:
        """Get all active sessions (without WebSocket connections)"""
        active_sessions = {}
        
        for session_id, session in self.sessions.items():
            if not session.is_expired():
                session_data = session.to_dict()
                session_data['websocket_count'] = len(session.websocket_connections)
                active_sessions[session_id] = session_data
        
        return active_sessions
    
    async def get_session_by_user_id(self, user_id: str) -> Optional[Session]:
        """Get session by Discord user ID"""
        for session in self.sessions.values():
            if session.user_id == user_id and not session.is_expired():
                return session
        
        # Try to load from storage
        sessions_data = await self.json_manager.read_json("sessions", {})
        for session_id, session_data in sessions_data.items():
            if session_data.get("user_id") == user_id:
                session = Session.from_dict(session_data)
                if not session.is_expired():
                    self.sessions[session_id] = session
                    return session
        
        return None
    
    async def _save_session(self, session: Session):
        """Save session to storage"""
        try:
            sessions_data = await self.json_manager.read_json("sessions", {})
            sessions_data[session.session_id] = session.to_dict()
            await self.json_manager.write_json("sessions", sessions_data)
        except Exception as e:
            self.logger.error(f"Failed to save session {session.session_id}: {e}")
    
    async def _load_session(self, session_id: str) -> Optional[Session]:
        """Load session from storage"""
        try:
            sessions_data = await self.json_manager.read_json("sessions", {})
            if session_id in sessions_data:
                return Session.from_dict(sessions_data[session_id])
        except Exception as e:
            self.logger.error(f"Failed to load session {session_id}: {e}")
        
        return None
    
    async def _delete_session(self, session_id: str):
        """Delete session from storage"""
        try:
            sessions_data = await self.json_manager.read_json("sessions", {})
            if session_id in sessions_data:
                del sessions_data[session_id]
                await self.json_manager.write_json("sessions", sessions_data)
        except Exception as e:
            self.logger.error(f"Failed to delete session {session_id}: {e}")
    
    async def shutdown(self):
        """Shutdown session manager"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # Save all active sessions
        for session in self.sessions.values():
            await self._save_session(session)
        
        self.logger.info("Session manager shutdown complete")

# Global session manager instance
_global_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    """Get or create global session manager instance"""
    global _global_session_manager
    
    if _global_session_manager is None:
        _global_session_manager = SessionManager()
    
    return _global_session_manager