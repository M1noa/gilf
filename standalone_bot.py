#!/usr/bin/env python3

import asyncio
import signal
import sys
import os
from typing import Optional
from config_manager import ConfigManager
from bot_process import BotProcess
from logger import get_logger
from discord_client import DiscordSelfBot
from command_handler import get_command_handler

class StandaloneBot:
    """Standalone bot that runs independently without web interface"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.bot_process: Optional[BotProcess] = None
        self.logger = get_logger()
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        
    async def initialize(self):
        """Initialize the standalone bot"""
        try:
            # Load configuration
            await self.config_manager.load_config()
            
            # Setup signal handlers
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            self.logger.info("Standalone bot initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize standalone bot: {e}")
            return False
            
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self.shutdown())
        
    async def start(self):
        """Start the standalone bot"""
        try:
            if not await self.initialize():
                return False
                
            # Check if we have a token and auto-start is enabled
            token = await self.config_manager.get_discord_token()
            auto_start = await self.config_manager.get_auto_start()
            
            if not token:
                self.logger.error("No Discord token configured. Please set a token first.")
                self.logger.info("Use the web interface or edit the config file to set your token.")
                return False
                
            if not auto_start:
                self.logger.info("Auto-start is disabled. Enable it in the configuration to start automatically.")
                return False
                
            # Start the bot
            self.running = True
            await self._start_bot_with_retry(token)
            
            # Keep running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error in standalone bot: {e}")
            return False
            
    async def _start_bot_with_retry(self, token: str):
        """Start bot with retry logic"""
        while self.running and self.reconnect_attempts < self.max_reconnect_attempts:
            try:
                self.logger.info(f"Starting bot (attempt {self.reconnect_attempts + 1}/{self.max_reconnect_attempts})")
                
                # Create new bot process
                self.bot_process = BotProcess()
                
                # Start the bot
                success, message = await self.bot_process.start_bot(token)
                
                if success:
                    self.logger.info("Bot started successfully")
                    self.reconnect_attempts = 0  # Reset on successful start
                    
                    # Monitor bot and handle disconnections
                    await self._monitor_bot()
                    
                else:
                    self.logger.error(f"Failed to start bot: {message}")
                    if "Invalid token" in message:
                        self.logger.error("Invalid token detected. Please update your token.")
                        break
                    
                    self.reconnect_attempts += 1
                    
            except Exception as e:
                self.logger.error(f"Error starting bot: {e}")
                self.reconnect_attempts += 1
                
            if self.running and self.reconnect_attempts < self.max_reconnect_attempts:
                delay = await self.config_manager.get_config().get("discord", {}).get("reconnect_delay", 30)
                self.logger.info(f"Retrying in {delay} seconds...")
                await asyncio.sleep(delay)
                
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.logger.error("Max reconnection attempts reached. Stopping bot.")
            self.running = False
            
    async def _monitor_bot(self):
        """Monitor bot status and handle disconnections"""
        while self.running and self.bot_process:
            try:
                status = await self.bot_process.get_bot_status()
                
                if not status.get("connected", False) and status.get("running", False):
                    self.logger.warning("Bot disconnected, attempting to reconnect...")
                    break
                    
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error monitoring bot: {e}")
                break
                
    async def shutdown(self):
        """Shutdown the standalone bot"""
        try:
            self.logger.info("Shutting down standalone bot...")
            self.running = False
            
            if self.bot_process:
                await self.bot_process.stop_bot()
                self.bot_process = None
                
            self.logger.info("Standalone bot shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
            
    async def set_token(self, token: str):
        """Set Discord token"""
        await self.config_manager.set_discord_token(token)
        self.logger.info("Token updated successfully")
        
    async def enable_auto_start(self, enabled: bool = True):
        """Enable or disable auto-start"""
        await self.config_manager.set_auto_start(enabled)
        self.logger.info(f"Auto-start {'enabled' if enabled else 'disabled'}")
        
    async def get_status(self) -> dict:
        """Get current bot status"""
        status = {
            "running": self.running,
            "reconnect_attempts": self.reconnect_attempts,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "bot_status": None
        }
        
        if self.bot_process:
            status["bot_status"] = await self.bot_process.get_bot_status()
            
        return status

async def main():
    """Main entry point for standalone bot"""
    bot = StandaloneBot()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "set-token":
            if len(sys.argv) < 3:
                print("Usage: python standalone_bot.py set-token <your_discord_token>")
                return
            token = sys.argv[2]
            await bot.set_token(token)
            print("Token set successfully")
            return
            
        elif command == "enable-autostart":
            await bot.enable_auto_start(True)
            print("Auto-start enabled")
            return
            
        elif command == "disable-autostart":
            await bot.enable_auto_start(False)
            print("Auto-start disabled")
            return
            
        elif command == "status":
            await bot.initialize()
            status = await bot.get_status()
            print(f"Bot Status: {status}")
            return
            
        elif command == "help":
            print("Available commands:")
            print("  set-token <token>     - Set Discord token")
            print("  enable-autostart      - Enable auto-start")
            print("  disable-autostart     - Disable auto-start")
            print("  status                - Show bot status")
            print("  help                  - Show this help")
            print("  (no command)          - Start the bot")
            return
    
    # Start the bot
    await bot.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Error: {e}")