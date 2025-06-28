#!/usr/bin/env python3

import os
import json
import asyncio
from typing import Optional, Dict, Any
from pathlib import Path
from logger import get_logger

class ConfigManager:
    """Manages local configuration including Discord tokens and bot settings"""
    
    def __init__(self, config_path: str = "data/config/bot_config.json"):
        self.config_path = Path(config_path)
        self.logger = get_logger()
        self.config: Dict[str, Any] = {}
        self._ensure_config_dir()
        
    def _ensure_config_dir(self):
        """Ensure config directory exists"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
    async def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.logger.info("Configuration loaded successfully")
            else:
                self.config = self._get_default_config()
                await self.save_config()
                self.logger.info("Created default configuration")
                
            return self.config
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            self.config = self._get_default_config()
            return self.config
            
    async def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self.logger.info("Configuration saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "discord": {
                "token": "",
                "auto_start": False,
                "reconnect_attempts": 5,
                "reconnect_delay": 30
            },
            "features": {
                "nitro_sniper": {
                    "enabled": False,
                    "delay_ms": 50,
                    "webhook_url": ""
                },
                "auto_responder": {
                    "enabled": False,
                    "responses": {}
                },
                "message_logger": {
                    "enabled": False,
                    "log_dms": True,
                    "log_guilds": []
                }
            },
            "web_interface": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 8000,
                "require_auth": False
            },
            "logging": {
                "level": "INFO",
                "file_logging": True,
                "console_logging": True
            }
        }
        
    async def get_discord_token(self) -> Optional[str]:
        """Get stored Discord token"""
        token = self.config.get("discord", {}).get("token", "")
        return token if token else None
        
    async def set_discord_token(self, token: str):
        """Set Discord token"""
        if "discord" not in self.config:
            self.config["discord"] = {}
        self.config["discord"]["token"] = token
        await self.save_config()
        self.logger.info("Discord token updated")
        
    async def get_auto_start(self) -> bool:
        """Check if bot should auto-start"""
        return self.config.get("discord", {}).get("auto_start", False)
        
    async def set_auto_start(self, enabled: bool):
        """Set auto-start preference"""
        if "discord" not in self.config:
            self.config["discord"] = {}
        self.config["discord"]["auto_start"] = enabled
        await self.save_config()
        self.logger.info(f"Auto-start {'enabled' if enabled else 'disabled'}")
        
    async def get_feature_config(self, feature: str) -> Dict[str, Any]:
        """Get configuration for a specific feature"""
        return self.config.get("features", {}).get(feature, {})
        
    async def set_feature_config(self, feature: str, config: Dict[str, Any]):
        """Set configuration for a specific feature"""
        if "features" not in self.config:
            self.config["features"] = {}
        self.config["features"][feature] = config
        await self.save_config()
        self.logger.info(f"Feature '{feature}' configuration updated")
        
    async def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.config.get("features", {}).get(feature, {}).get("enabled", False)
        
    async def enable_feature(self, feature: str, enabled: bool = True):
        """Enable or disable a feature"""
        if "features" not in self.config:
            self.config["features"] = {}
        if feature not in self.config["features"]:
            self.config["features"][feature] = {}
        self.config["features"][feature]["enabled"] = enabled
        await self.save_config()
        self.logger.info(f"Feature '{feature}' {'enabled' if enabled else 'disabled'}")
        
    async def get_web_config(self) -> Dict[str, Any]:
        """Get web interface configuration"""
        return self.config.get("web_interface", {})
        
    async def clear_token(self):
        """Clear stored Discord token"""
        if "discord" in self.config:
            self.config["discord"]["token"] = ""
            await self.save_config()
            self.logger.info("Discord token cleared")
            
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        return self.config.copy()
        
    async def update_config(self, updates: Dict[str, Any]):
        """Update configuration with new values"""
        def deep_update(base_dict, update_dict):
            for key, value in update_dict.items():
                if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
                    deep_update(base_dict[key], value)
                else:
                    base_dict[key] = value
                    
        deep_update(self.config, updates)
        await self.save_config()
        self.logger.info("Configuration updated")