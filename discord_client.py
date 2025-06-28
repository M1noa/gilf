import discord
import asyncio
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import time
from logger import get_logger
from session_manager import get_session_manager
from json_manager import JSONManager

class RateLimiter:
    def __init__(self):
        self.requests = {}
        self.logger = get_logger()
    
    async def wait_if_rate_limited(self, endpoint: str, max_requests: int = 50, window_seconds: int = 60):
        """Wait if rate limited for specific endpoint"""
        now = time.time()
        
        if endpoint not in self.requests:
            self.requests[endpoint] = []
        
        # Clean old requests
        self.requests[endpoint] = [
            req_time for req_time in self.requests[endpoint]
            if now - req_time < window_seconds
        ]
        
        # Check if rate limited
        if len(self.requests[endpoint]) >= max_requests:
            wait_time = window_seconds - (now - self.requests[endpoint][0])
            if wait_time > 0:
                self.logger.warning(f"Rate limited on {endpoint}, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
        
        # Add current request
        self.requests[endpoint].append(now)

class MessageQueue:
    def __init__(self, max_size: int = 1000):
        self.queue = asyncio.Queue(maxsize=max_size)
        self.logger = get_logger()
        self.processing = False
    
    async def add_event(self, event_type: str, data: Dict[str, Any]):
        """Add event to queue"""
        try:
            event = {
                "type": event_type,
                "data": data,
                "timestamp": datetime.now().isoformat()
            }
            await self.queue.put(event)
        except asyncio.QueueFull:
            self.logger.warning(f"Message queue full, dropping event: {event_type}")
    
    async def process_events(self, handler):
        """Process events from queue"""
        self.processing = True
        
        while self.processing:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await handler(event)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error processing event: {e}")
    
    def stop_processing(self):
        """Stop processing events"""
        self.processing = False

class DiscordSelfBot(discord.Client):
    def __init__(self, session_id: str, **kwargs):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.presences = True
        intents.message_content = True
        
        super().__init__(intents=intents, **kwargs)
        
        self.session_id = session_id
        self.logger = get_logger()
        self.session_manager = get_session_manager()
        self.json_manager = JSONManager()
        self.rate_limiter = RateLimiter()
        self.message_queue = MessageQueue()
        
        # Connection management
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5
        self.last_heartbeat = None
        self.connection_stable = False
        
        # Event processing
        self.event_processor_task = None
        
        # User data cache
        self.user_data_cache = {}
        self.cache_expiry = timedelta(minutes=5)
        self.last_cache_update = None

    async def wait_until_ready(self):
        """Wait until the bot is ready."""
        await self.wait_for('ready')
    
    async def on_ready(self):
        """Enhanced on_ready with comprehensive user data"""
        try:
            self.logger.info(f"Bot ready! Logged in as {self.user}")
            self.connection_stable = True
            self.reconnect_attempts = 0
            
            # Mark session as Discord ready
            await self.session_manager.set_discord_ready(self.session_id, True)
            
            # Get comprehensive user data
            user_data = await self._get_comprehensive_user_data()
            
            # Send to session
            await self.session_manager.broadcast_to_session(self.session_id, {
                "type": "discord_ready",
                "data": user_data
            })
            
            # Cache the data
            self.user_data_cache = user_data
            self.last_cache_update = datetime.now()
            
            # Log the event
            await self.logger.log_discord_event("ready", {
                "user_id": str(self.user.id),
                "username": self.user.name,
                "guild_count": len(self.guilds)
            })
            
        except Exception as e:
            self.logger.error(f"Error in on_ready: {e}", exc_info=True)
            await self._send_error_to_session("ready_error", str(e))

    async def on_disconnect(self):
        """Handle disconnection"""
        self.logger.warning("Discord client disconnected")
        self.connection_stable = False
        
        await self.session_manager.set_discord_ready(self.session_id, False)
        await self.session_manager.broadcast_to_session(self.session_id, {
            "type": "discord_disconnected",
            "data": {"timestamp": datetime.now().isoformat()}
        })
    
    async def on_resumed(self):
        """Handle connection resume"""
        self.logger.info("Discord connection resumed")
        self.connection_stable = True
        self.reconnect_attempts = 0
        
        await self.session_manager.broadcast_to_session(self.session_id, {
            "type": "discord_resumed",
            "data": {"timestamp": datetime.now().isoformat()}
        })
    
    async def on_error(self, event, *args, **kwargs):
        """Enhanced error handling"""
        self.logger.error(f"Discord error in event {event}: {args}", exc_info=True)
        
        await self._send_error_to_session("discord_event_error", {
            "event": event,
            "args": str(args)[:500]  # Limit length
        })
    
    async def on_guild_join(self, guild):
        """Handle guild join"""
        await self.message_queue.add_event("guild_join", {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "member_count": guild.member_count
        })
    
    async def on_guild_remove(self, guild):
        """Handle guild leave"""
        await self.message_queue.add_event("guild_remove", {
            "guild_id": str(guild.id),
            "guild_name": guild.name
        })
    
    async def on_message(self, message):
        """Handle messages (for potential command processing)"""
        if message.author == self.user:
            await self.message_queue.add_event("self_message", {
                "channel_id": str(message.channel.id),
                "content": message.content[:100],  # Limit content length
                "timestamp": message.created_at.isoformat()
            })
    
    async def _get_comprehensive_user_data(self) -> Dict[str, Any]:
        """Get comprehensive user data with rate limiting"""
        try:
            await self.rate_limiter.wait_if_rate_limited("user_data")
            
            # Basic user info
            user_data = {
                "id": str(self.user.id),
                "username": self.user.name,
                "discriminator": self.user.discriminator,
                "display_name": self.user.display_name or self.user.name,
                "avatar_url": str(self.user.avatar.url) if self.user.avatar else None,
                "bot": self.user.bot,
                "created_at": self.user.created_at.isoformat()
            }
            
            # Flags and badges
            if hasattr(self.user, 'public_flags'):
                user_data["badges"] = [flag.name for flag in self.user.public_flags.all()]
            else:
                user_data["badges"] = []
            
            # Guild information
            user_data["guild_count"] = len(self.guilds)
            user_data["guilds"] = []
            
            for guild in self.guilds[:50]:  # Limit to first 50 guilds
                try:
                    guild_data = {
                        "id": str(guild.id),
                        "name": guild.name,
                        "member_count": guild.member_count,
                        "owner": guild.owner_id == self.user.id if guild.owner_id else False
                    }
                    user_data["guilds"].append(guild_data)
                except Exception as e:
                    self.logger.debug(f"Error getting guild data for {guild.id}: {e}")
            
            # Friends count (if available)
            try:
                friends = await self._get_friends_safely()
                user_data["friend_count"] = len(friends)
                user_data["friends"] = friends[:20]  # Limit to first 20 friends
            except Exception as e:
                self.logger.debug(f"Could not get friends: {e}")
                user_data["friend_count"] = 0
                user_data["friends"] = []
            
            # Nitro status detection
            user_data["nitro_type"] = await self._detect_nitro_status()
            
            # Limits based on Nitro status
            limits = self._get_discord_limits(user_data["nitro_type"])
            user_data["limits"] = limits
            
            return user_data
            
        except Exception as e:
            self.logger.error(f"Error getting comprehensive user data: {e}", exc_info=True)
            return {
                "id": str(self.user.id) if self.user else "unknown",
                "username": self.user.name if self.user else "unknown",
                "error": str(e)
            }
    
    async def _get_friends_safely(self) -> List[Dict[str, Any]]:
        """Safely get friends list"""
        friends = []
        
        try:
            # This might not work for all self-bots
            if hasattr(self, 'friends'):
                for friend in self.friends:
                    friends.append({
                        "id": str(friend.id),
                        "username": friend.name,
                        "discriminator": friend.discriminator,
                        "display_name": friend.display_name or friend.name
                    })
        except Exception as e:
            self.logger.debug(f"Friends list not accessible: {e}")
        
        return friends
    
    async def _detect_nitro_status(self) -> str:
        """Detect Nitro subscription status"""
        try:
            # Check for Nitro indicators
            if hasattr(self.user, 'premium_type'):
                if self.user.premium_type == 1:
                    return "nitro_classic"
                elif self.user.premium_type == 2:
                    return "nitro"
                elif self.user.premium_type == 3:
                    return "nitro_basic"
            
            # Check badges for Nitro indicators
            if hasattr(self.user, 'public_flags'):
                flags = [flag.name for flag in self.user.public_flags.all()]
                if 'premium' in flags or 'nitro' in flags:
                    return "nitro"
            
            return "none"
            
        except Exception as e:
            self.logger.debug(f"Could not detect Nitro status: {e}")
            return "unknown"
    
    def _get_discord_limits(self, nitro_type: str) -> Dict[str, int]:
        """Get Discord limits based on Nitro status"""
        limits = {
            "none": {
                "guilds": 100,
                "friends": 1000,
                "file_size_mb": 8,
                "emoji_slots": 50
            },
            "nitro_classic": {
                "guilds": 100,
                "friends": 1000,
                "file_size_mb": 50,
                "emoji_slots": 50
            },
            "nitro": {
                "guilds": 200,
                "friends": 1000,
                "file_size_mb": 100,
                "emoji_slots": 200
            },
            "nitro_basic": {
                "guilds": 100,
                "friends": 1000,
                "file_size_mb": 25,
                "emoji_slots": 50
            }
        }
        
        return limits.get(nitro_type, limits["none"])
    
    async def _handle_queued_event(self, event: Dict[str, Any]):
        """Handle events from the message queue"""
        try:
            event_type = event["type"]
            event_data = event["data"]
            
            # Log the event
            await self.logger.log_discord_event(event_type, event_data)
            
            # Send to session
            await self.session_manager.broadcast_to_session(self.session_id, {
                "type": f"discord_{event_type}",
                "data": event_data
            })
            
            # Update cached data if needed
            if event_type in ["guild_join", "guild_remove"]:
                await self._invalidate_user_cache()
            
        except Exception as e:
            self.logger.error(f"Error handling queued event: {e}", exc_info=True)
    
    async def _invalidate_user_cache(self):
        """Invalidate user data cache"""
        self.last_cache_update = None
        self.user_data_cache = {}
    
    async def _send_error_to_session(self, error_type: str, error_message: str):
        """Send error message to session"""
        try:
            await self.session_manager.broadcast_to_session(self.session_id, {
                "type": "error",
                "data": {
                    "error_type": error_type,
                    "message": error_message,
                    "timestamp": datetime.now().isoformat()
                }
            })
        except Exception as e:
            self.logger.error(f"Failed to send error to session: {e}")
    
    async def get_cached_user_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Get user data from cache or refresh if needed"""
        now = datetime.now()
        
        if (force_refresh or 
            not self.user_data_cache or 
            not self.last_cache_update or 
            now - self.last_cache_update > self.cache_expiry):
            
            self.user_data_cache = await self._get_comprehensive_user_data()
            self.last_cache_update = now
        
        return self.user_data_cache
    
    async def close_bot(self):
        """Properly close the bot"""
        try:
            self.logger.info(f"Closing Discord bot for session {self.session_id}")
            
            # Stop event processing
            if self.event_processor_task:
                self.message_queue.stop_processing()
                self.event_processor_task.cancel()
            
            # Mark session as not ready
            await self.session_manager.set_discord_ready(self.session_id, False)
            
            # Close Discord connection
            await self.close()
            
        except Exception as e:
            self.logger.error(f"Error closing bot: {e}", exc_info=True)
    
    @property
    def friends(self):
        """Get friends list (compatibility method)"""
        try:
            return getattr(self, '_friends', [])
        except:
            return []
    
    def get_user_data(self):
        """Get basic user data (compatibility method)"""
        if not self.user:
            return {}
        
        return {
            "username": self.user.name,
            "id": str(self.user.id),
            "display_name": self.user.display_name or self.user.name,
            "guild_count": len(self.guilds),
            "friend_count": len(self.friends)
        }