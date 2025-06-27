import asyncio
import os
import signal
import sys
from typing import Optional
from discord_client import DiscordSelfBot
from command_handler import get_command_handler
from token_manager import TokenManager
from logger import get_logger
from session_manager import get_session_manager
from json_manager import JSONManager

class BotProcess:
    def __init__(self):
        self.bot: Optional[DiscordSelfBot] = None
        self.token_manager = TokenManager()
        self.logger = get_logger()
        self.session_manager = get_session_manager()
        self.json_manager = JSONManager()
        self.command_handler = get_command_handler()
        self.running = False
        
        # Don't setup signal handlers here - let the main app handle signals
        # through the lifespan manager to avoid conflicts
    

    
    async def _shutdown_bot(self):
        """Internal method to shutdown the bot gracefully"""
        try:
            await self.stop_bot()
        except Exception as e:
            self.logger.error(f"Error during bot shutdown: {e}")
        finally:
            # Force exit if still running
            if self.running:
                self.logger.warning("Forcing process exit")
                os._exit(0)
    
    async def start_bot(self, token: str, session_id: str = None) -> bool:
        """Start the Discord bot"""
        try:
            self.logger.info("Starting Discord bot process...")
            
            # Load command statistics
            await self.command_handler.load_command_stats()
            
            # Create bot instance
            self.bot = DiscordSelfBot(session_id=session_id)
            
            # Add command handler to bot
            @self.bot.event
            async def on_message(message):
                # Don't respond to own messages
                if message.author == self.bot.user:
                    return
                
                # Process commands
                await self.command_handler.process_message(message, self.bot)
            
            # Start the bot
            self.running = True
            await self.bot.start(token)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start bot: {e}", exc_info=True)
            return False
    
    async def stop_bot(self):
        """Stop the Discord bot"""
        try:
            self.logger.info("Stopping Discord bot...")
            self.running = False
            
            # Save command statistics
            await self.command_handler.save_command_stats()
            
            if self.bot:
                await self.bot.close_bot()
                self.bot = None
            
            self.logger.info("Bot stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping bot: {e}", exc_info=True)
    
    async def restart_bot(self, token: str, session_id: str = None):
        """Restart the Discord bot"""
        self.logger.info("Restarting Discord bot...")
        
        await self.stop_bot()
        await asyncio.sleep(2)  # Brief pause
        await self.start_bot(token, session_id)
    
    async def get_bot_status(self) -> dict:
        """Get current bot status"""
        status = {
            "running": self.running,
            "connected": False,
            "user_data": None,
            "latency": None,
            "guilds": 0,
            "uptime": None
        }
        
        if self.bot:
            status["connected"] = not self.bot.is_closed()
            status["latency"] = round(self.bot.latency * 1000) if self.bot.latency else None
            status["guilds"] = len(self.bot.guilds) if self.bot.guilds else 0
            
            try:
                status["user_data"] = await self.bot.get_cached_user_data()
            except Exception as e:
                self.logger.error(f"Failed to get user data: {e}")
        
        return status
    
    async def run_maintenance(self):
        """Run maintenance tasks"""
        try:
            self.logger.info("Running maintenance tasks...")
            
            # Clean up old logs
            from logger import cleanup_old_logs
            cleanup_old_logs()
            
            # Clean up expired sessions
            await self.session_manager.cleanup_expired_sessions()
            
            # Save command statistics
            await self.command_handler.save_command_stats()
            
            self.logger.info("Maintenance tasks completed")
            
        except Exception as e:
            self.logger.error(f"Error during maintenance: {e}", exc_info=True)
    
    async def handle_websocket_message(self, message: dict, session_id: str):
        """Handle WebSocket messages from web interface"""
        try:
            message_type = message.get("type")
            
            if message_type == "start_bot":
                token = message.get("token")
                if not token:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": "No token provided"}
                    )
                    return
                
                # Validate token format
                if not self.token_manager.validate_token_format(token):
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": "Invalid token format"}
                    )
                    return
                
                # Start bot
                success = await self.start_bot(token, session_id)
                if success:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "bot_started", "message": "Bot started successfully"}
                    )
                else:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": "Failed to start bot"}
                    )
            
            elif message_type == "stop_bot":
                await self.stop_bot()
                await self.session_manager.send_to_session(
                    session_id, {"type": "bot_stopped", "message": "Bot stopped"}
                )
            
            elif message_type == "restart_bot":
                token = message.get("token")
                if token:
                    await self.restart_bot(token, session_id)
                    await self.session_manager.send_to_session(
                        session_id, {"type": "bot_restarted", "message": "Bot restarted"}
                    )
                else:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": "No token provided for restart"}
                    )
            
            elif message_type == "get_status":
                status = await self.get_bot_status()
                await self.session_manager.send_to_session(
                    session_id, {"type": "bot_status", "data": status}
                )
            
            elif message_type == "get_commands":
                commands = await self.command_handler.get_command_list()
                await self.session_manager.send_to_session(
                    session_id, {"type": "commands_list", "data": commands}
                )
            
            elif message_type == "save_token":
                token = message.get("token")
                name = message.get("name", "default")
                
                if token and self.token_manager.validate_token_format(token):
                    success = await self.token_manager.store_token(name, token)
                    if success:
                        await self.session_manager.send_to_session(
                            session_id, {"type": "token_saved", "message": f"Token '{name}' saved"}
                        )
                    else:
                        await self.session_manager.send_to_session(
                            session_id, {"type": "error", "message": "Failed to save token"}
                        )
                else:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": "Invalid token"}
                    )
            
            elif message_type == "load_token":
                name = message.get("name", "default")
                token = await self.token_manager.load_token(name)
                
                if token:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "token_loaded", "data": {"name": name, "token": token}}
                    )
                else:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": f"Token '{name}' not found"}
                    )
            
            elif message_type == "list_tokens":
                tokens = await self.token_manager.list_tokens()
                await self.session_manager.send_to_session(
                    session_id, {"type": "tokens_list", "data": tokens}
                )
            
            elif message_type == "delete_token":
                name = message.get("name")
                if name:
                    success = await self.token_manager.delete_token(name)
                    if success:
                        await self.session_manager.send_to_session(
                            session_id, {"type": "token_deleted", "message": f"Token '{name}' deleted"}
                        )
                    else:
                        await self.session_manager.send_to_session(
                            session_id, {"type": "error", "message": f"Failed to delete token '{name}'"}
                        )
                else:
                    await self.session_manager.send_to_session(
                        session_id, {"type": "error", "message": "No token name provided"}
                    )
            
            else:
                await self.session_manager.send_to_session(
                    session_id, {"type": "error", "message": f"Unknown message type: {message_type}"}
                )
        
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
            await self.session_manager.send_to_session(
                session_id, {"type": "error", "message": "Internal server error"}
            )

async def main():
    """Main bot process entry point"""
    bot_process = BotProcess()
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        token = sys.argv[1]
        session_id = sys.argv[2] if len(sys.argv) > 2 else None
        
        # Start bot with provided token
        await bot_process.start_bot(token, session_id)
    else:
        # Interactive mode - wait for WebSocket commands
        bot_process.logger.info("Bot process started in interactive mode")
        
        # Keep the process running
        try:
            while True:
                await asyncio.sleep(1)
                
                # Run maintenance every hour
                if hasattr(bot_process, '_last_maintenance'):
                    import time
                    if time.time() - bot_process._last_maintenance > 3600:
                        await bot_process.run_maintenance()
                        bot_process._last_maintenance = time.time()
                else:
                    import time
                    bot_process._last_maintenance = time.time()
        
        except KeyboardInterrupt:
            bot_process.logger.info("Received keyboard interrupt")
        finally:
            await bot_process.stop_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot process terminated by user")
    except Exception as e:
        print(f"Fatal error in bot process: {e}")
        sys.exit(1)