import asyncio
import re
from typing import Dict, List, Callable, Any, Optional
from datetime import datetime
from logger import get_logger
from session_manager import get_session_manager
from json_manager import JSONManager

class Command:
    def __init__(self, name: str, func: Callable, description: str = "", 
                 aliases: List[str] = None, admin_only: bool = False,
                 cooldown: int = 0, usage: str = ""):
        self.name = name
        self.func = func
        self.description = description
        self.aliases = aliases or []
        self.admin_only = admin_only
        self.cooldown = cooldown
        self.usage = usage
        self.last_used = {}
    
    def can_execute(self, user_id: str) -> tuple[bool, str]:
        """Check if user can execute this command"""
        now = datetime.now()
        
        # Check cooldown
        if user_id in self.last_used:
            time_diff = (now - self.last_used[user_id]).total_seconds()
            if time_diff < self.cooldown:
                remaining = self.cooldown - time_diff
                return False, f"Command on cooldown. Wait {remaining:.1f}s"
        
        return True, ""
    
    def mark_used(self, user_id: str):
        """Mark command as used by user"""
        self.last_used[user_id] = datetime.now()

class CommandHandler:
    def __init__(self, prefix: str = "!"):
        self.prefix = prefix
        self.commands: Dict[str, Command] = {}
        self.logger = get_logger()
        self.session_manager = get_session_manager()
        self.json_manager = JSONManager()
        
        # Command statistics
        self.command_stats = {}
        
        # Register default commands
        self._register_default_commands()
    
    def command(self, name: str = None, description: str = "", aliases: List[str] = None,
                admin_only: bool = False, cooldown: int = 0, usage: str = ""):
        """Decorator for registering commands"""
        def decorator(func):
            cmd_name = name or func.__name__
            cmd = Command(
                name=cmd_name,
                func=func,
                description=description,
                aliases=aliases or [],
                admin_only=admin_only,
                cooldown=cooldown,
                usage=usage
            )
            self.register_command(cmd)
            return func
        return decorator
    
    def register_command(self, command: Command):
        """Register a command"""
        self.commands[command.name] = command
        
        # Register aliases
        for alias in command.aliases:
            self.commands[alias] = command
        
        self.logger.info(f"Registered command: {command.name}")
    
    def unregister_command(self, name: str):
        """Unregister a command"""
        if name in self.commands:
            command = self.commands[name]
            
            # Remove main command and aliases
            del self.commands[name]
            for alias in command.aliases:
                if alias in self.commands:
                    del self.commands[alias]
            
            self.logger.info(f"Unregistered command: {name}")
    
    async def process_message(self, message, bot_instance):
        """Process a message for commands"""
        if not message.content.startswith(self.prefix):
            return False
        
        # Parse command
        content = message.content[len(self.prefix):].strip()
        if not content:
            return False
        
        parts = content.split()
        command_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Find command
        if command_name not in self.commands:
            await self._send_error(message, f"Unknown command: {command_name}")
            return False
        
        command = self.commands[command_name]
        user_id = str(message.author.id)
        
        # Check if user can execute
        can_execute, error_msg = command.can_execute(user_id)
        if not can_execute:
            await self._send_error(message, error_msg)
            return False
        
        try:
            # Execute command
            await command.func(message, args, bot_instance)
            command.mark_used(user_id)
            
            # Update statistics
            self._update_command_stats(command_name, user_id)
            
            self.logger.info(f"Executed command {command_name} by {user_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error executing command {command_name}: {e}", exc_info=True)
            await self._send_error(message, f"Error executing command: {str(e)}")
            return False
    
    def _update_command_stats(self, command_name: str, user_id: str):
        """Update command usage statistics"""
        if command_name not in self.command_stats:
            self.command_stats[command_name] = {
                "total_uses": 0,
                "unique_users": set(),
                "last_used": None
            }
        
        stats = self.command_stats[command_name]
        stats["total_uses"] += 1
        stats["unique_users"].add(user_id)
        stats["last_used"] = datetime.now()
    
    async def _send_error(self, message, error_text: str):
        """Send error message"""
        try:
            await message.channel.send(f"❌ {error_text}")
        except Exception as e:
            self.logger.error(f"Failed to send error message: {e}")
    
    async def _send_success(self, message, success_text: str):
        """Send success message"""
        try:
            await message.channel.send(f"✅ {success_text}")
        except Exception as e:
            self.logger.error(f"Failed to send success message: {e}")
    
    def _register_default_commands(self):
        """Register default bot commands"""
        
        @self.command(name="help", description="Show available commands", aliases=["h"])
        async def help_command(message, args, bot):
            if args and args[0] in self.commands:
                # Show specific command help
                cmd = self.commands[args[0]]
                embed_text = f"**{cmd.name}**\n"
                embed_text += f"Description: {cmd.description or 'No description'}\n"
                if cmd.aliases:
                    embed_text += f"Aliases: {', '.join(cmd.aliases)}\n"
                if cmd.usage:
                    embed_text += f"Usage: {self.prefix}{cmd.usage}\n"
                if cmd.cooldown > 0:
                    embed_text += f"Cooldown: {cmd.cooldown}s\n"
                
                await message.channel.send(embed_text)
            else:
                # Show all commands
                embed_text = f"**Available Commands** (Prefix: {self.prefix})\n\n"
                
                # Group commands by category
                seen_commands = set()
                for cmd_name, cmd in self.commands.items():
                    if cmd.name in seen_commands or cmd_name != cmd.name:
                        continue
                    
                    seen_commands.add(cmd.name)
                    embed_text += f"**{cmd.name}** - {cmd.description or 'No description'}\n"
                
                embed_text += f"\nUse `{self.prefix}help <command>` for detailed info"
                await message.channel.send(embed_text)
        
        @self.command(name="ping", description="Check bot latency", cooldown=5)
        async def ping_command(message, args, bot):
            latency = round(bot.latency * 1000)
            await message.channel.send(f"🏓 Pong! Latency: {latency}ms")
        
        @self.command(name="stats", description="Show bot statistics", cooldown=10)
        async def stats_command(message, args, bot):
            stats_text = "**Bot Statistics**\n\n"
            stats_text += f"Guilds: {len(bot.guilds)}\n"
            stats_text += f"Users: {len(bot.users)}\n"
            
            # Command stats
            if self.command_stats:
                stats_text += "\n**Command Usage:**\n"
                for cmd_name, stats in self.command_stats.items():
                    if cmd_name in [cmd.name for cmd in self.commands.values()]:
                        stats_text += f"{cmd_name}: {stats['total_uses']} uses\n"
            
            await message.channel.send(stats_text)
        
        @self.command(name="userinfo", description="Show user information", aliases=["ui"])
        async def userinfo_command(message, args, bot):
            user_data = await bot.get_cached_user_data()
            
            info_text = "**User Information**\n\n"
            info_text += f"Username: {user_data.get('username', 'Unknown')}\n"
            info_text += f"ID: {user_data.get('id', 'Unknown')}\n"
            info_text += f"Display Name: {user_data.get('display_name', 'Unknown')}\n"
            info_text += f"Guilds: {user_data.get('guild_count', 0)}\n"
            info_text += f"Friends: {user_data.get('friend_count', 0)}\n"
            
            nitro_type = user_data.get('nitro_type', 'none')
            if nitro_type != 'none':
                info_text += f"Nitro: {nitro_type.replace('_', ' ').title()}\n"
            
            badges = user_data.get('badges', [])
            if badges:
                info_text += f"Badges: {', '.join(badges)}\n"
            
            await message.channel.send(info_text)
        
        @self.command(name="reload", description="Reload bot configuration", admin_only=True)
        async def reload_command(message, args, bot):
            try:
                # Reload configuration or perform maintenance tasks
                await self._send_success(message, "Bot configuration reloaded")
            except Exception as e:
                await self._send_error(message, f"Failed to reload: {str(e)}")
        
        @self.command(name="eval", description="Evaluate Python code", admin_only=True)
        async def eval_command(message, args, bot):
            if not args:
                await self._send_error(message, "No code provided")
                return
            
            code = " ".join(args)
            
            # Security check - basic filtering
            dangerous_keywords = ['import', 'exec', 'eval', '__', 'open', 'file']
            if any(keyword in code.lower() for keyword in dangerous_keywords):
                await self._send_error(message, "Dangerous code detected")
                return
            
            try:
                result = eval(code)
                await message.channel.send(f"Result: `{result}`")
            except Exception as e:
                await self._send_error(message, f"Error: {str(e)}")
        
        @self.command(name="guilds", description="List bot guilds", cooldown=30)
        async def guilds_command(message, args, bot):
            user_data = await bot.get_cached_user_data()
            guilds = user_data.get('guilds', [])
            
            if not guilds:
                await message.channel.send("No guild information available")
                return
            
            guild_text = "**Bot Guilds:**\n\n"
            for i, guild in enumerate(guilds[:10]):  # Limit to 10
                guild_text += f"{i+1}. {guild.get('name', 'Unknown')} "
                guild_text += f"({guild.get('member_count', 0)} members)\n"
            
            if len(guilds) > 10:
                guild_text += f"\n... and {len(guilds) - 10} more guilds"
            
            await message.channel.send(guild_text)
    
    async def get_command_list(self) -> List[Dict[str, Any]]:
        """Get list of all commands for API"""
        commands = []
        seen_commands = set()
        
        for cmd_name, cmd in self.commands.items():
            if cmd.name in seen_commands or cmd_name != cmd.name:
                continue
            
            seen_commands.add(cmd.name)
            
            command_info = {
                "name": cmd.name,
                "description": cmd.description,
                "aliases": cmd.aliases,
                "admin_only": cmd.admin_only,
                "cooldown": cmd.cooldown,
                "usage": cmd.usage,
                "stats": self.command_stats.get(cmd.name, {
                    "total_uses": 0,
                    "unique_users": 0,
                    "last_used": None
                })
            }
            
            # Convert set to count for JSON serialization
            if cmd.name in self.command_stats:
                command_info["stats"]["unique_users"] = len(
                    self.command_stats[cmd.name]["unique_users"]
                )
            
            commands.append(command_info)
        
        return commands
    
    async def save_command_stats(self):
        """Save command statistics to file"""
        try:
            # Convert sets to lists for JSON serialization
            serializable_stats = {}
            for cmd_name, stats in self.command_stats.items():
                serializable_stats[cmd_name] = {
                    "total_uses": stats["total_uses"],
                    "unique_users": list(stats["unique_users"]),
                    "last_used": stats["last_used"].isoformat() if stats["last_used"] else None
                }
            
            await self.json_manager.write_json("command_stats", serializable_stats)
            self.logger.info("Command statistics saved")
            
        except Exception as e:
            self.logger.error(f"Failed to save command stats: {e}")
    
    async def load_command_stats(self):
        """Load command statistics from file"""
        try:
            stats_data = await self.json_manager.read_json("command_stats", {})
            
            for cmd_name, stats in stats_data.items():
                self.command_stats[cmd_name] = {
                    "total_uses": stats.get("total_uses", 0),
                    "unique_users": set(stats.get("unique_users", [])),
                    "last_used": datetime.fromisoformat(stats["last_used"]) if stats.get("last_used") else None
                }
            
            self.logger.info("Command statistics loaded")
            
        except Exception as e:
            self.logger.error(f"Failed to load command stats: {e}")
    
    def set_prefix(self, new_prefix: str):
        """Change command prefix"""
        old_prefix = self.prefix
        self.prefix = new_prefix
        self.logger.info(f"Command prefix changed from '{old_prefix}' to '{new_prefix}'")
    
    def get_prefix(self) -> str:
        """Get current command prefix"""
        return self.prefix

# Global command handler instance
_global_command_handler: Optional[CommandHandler] = None

def get_command_handler() -> CommandHandler:
    """Get or create global command handler instance"""
    global _global_command_handler
    
    if _global_command_handler is None:
        _global_command_handler = CommandHandler()
    
    return _global_command_handler