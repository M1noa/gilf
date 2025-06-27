import json
import os
import shutil
import asyncio
import aiofiles
from typing import Any, Dict, Optional
from datetime import datetime
import logging

class JSONManager:
    def __init__(self, base_path="data/json"):
        self.base_path = base_path
        self.backup_path = "data/backups"
        self.logger = logging.getLogger(__name__)
        
        # Ensure directories exist
        os.makedirs(self.base_path, exist_ok=True)
        os.makedirs(self.backup_path, exist_ok=True)
    
    def _get_file_path(self, filename: str) -> str:
        """Get full file path"""
        if not filename.endswith('.json'):
            filename += '.json'
        return os.path.join(self.base_path, filename)
    
    def _get_backup_path(self, filename: str) -> str:
        """Get backup file path with timestamp"""
        if not filename.endswith('.json'):
            filename += '.json'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{filename.replace('.json', '')}_{timestamp}.json"
        return os.path.join(self.backup_path, backup_name)
    
    async def read_json(self, filename: str, default: Any = None) -> Any:
        """Safely read JSON file with corruption handling"""
        file_path = self._get_file_path(filename)
        
        if not os.path.exists(file_path):
            self.logger.info(f"File {filename} doesn't exist, returning default value")
            return default
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                
            # Validate JSON before parsing
            if not content.strip():
                self.logger.warning(f"File {filename} is empty, returning default value")
                return default
            
            data = json.loads(content)
            self.logger.debug(f"Successfully read {filename}")
            return data
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON corruption detected in {filename}: {e}")
            
            # Try to restore from backup
            restored_data = await self._restore_from_backup(filename)
            if restored_data is not None:
                self.logger.info(f"Restored {filename} from backup")
                return restored_data
            
            self.logger.warning(f"Could not restore {filename}, returning default value")
            return default
            
        except Exception as e:
            self.logger.error(f"Error reading {filename}: {e}")
            return default
    
    async def write_json(self, filename: str, data: Any, create_backup: bool = True) -> bool:
        """Safely write JSON file with atomic operations"""
        file_path = self._get_file_path(filename)
        temp_path = file_path + '.tmp'
        
        try:
            # Create backup if file exists and backup is requested
            if create_backup and os.path.exists(file_path):
                await self._create_backup(filename)
            
            # Write to temporary file first
            async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
                json_content = json.dumps(data, indent=2, ensure_ascii=False)
                await f.write(json_content)
            
            # Verify the written file is valid JSON
            async with aiofiles.open(temp_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                json.loads(content)  # Validate JSON
            
            # Atomic move
            shutil.move(temp_path, file_path)
            self.logger.debug(f"Successfully wrote {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error writing {filename}: {e}")
            
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            return False
    
    async def update_json(self, filename: str, updates: Dict[str, Any], merge: bool = True) -> bool:
        """Update JSON file with new data"""
        current_data = await self.read_json(filename, {})
        
        if merge and isinstance(current_data, dict) and isinstance(updates, dict):
            # Deep merge dictionaries
            merged_data = self._deep_merge(current_data, updates)
            return await self.write_json(filename, merged_data)
        else:
            # Replace entirely
            return await self.write_json(filename, updates)
    
    def _deep_merge(self, base: dict, updates: dict) -> dict:
        """Deep merge two dictionaries"""
        result = base.copy()
        
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    async def _create_backup(self, filename: str) -> bool:
        """Create backup of existing file"""
        file_path = self._get_file_path(filename)
        backup_path = self._get_backup_path(filename)
        
        try:
            if os.path.exists(file_path):
                shutil.copy2(file_path, backup_path)
                self.logger.debug(f"Created backup: {backup_path}")
                return True
        except Exception as e:
            self.logger.error(f"Error creating backup for {filename}: {e}")
        
        return False
    
    async def _restore_from_backup(self, filename: str) -> Optional[Any]:
        """Try to restore from the most recent backup"""
        try:
            # Find most recent backup
            backup_files = []
            for f in os.listdir(self.backup_path):
                if f.startswith(filename.replace('.json', '')) and f.endswith('.json'):
                    backup_files.append(f)
            
            if not backup_files:
                return None
            
            # Sort by timestamp (newest first)
            backup_files.sort(reverse=True)
            latest_backup = os.path.join(self.backup_path, backup_files[0])
            
            # Try to read the backup
            async with aiofiles.open(latest_backup, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
            
            # Restore the backup to main file
            await self.write_json(filename, data, create_backup=False)
            return data
            
        except Exception as e:
            self.logger.error(f"Error restoring from backup: {e}")
            return None
    
    async def delete_file(self, filename: str, create_backup: bool = True) -> bool:
        """Delete JSON file with optional backup"""
        file_path = self._get_file_path(filename)
        
        try:
            if os.path.exists(file_path):
                if create_backup:
                    await self._create_backup(filename)
                
                os.remove(file_path)
                self.logger.info(f"Deleted {filename}")
                return True
        except Exception as e:
            self.logger.error(f"Error deleting {filename}: {e}")
        
        return False
    
    async def list_files(self) -> list:
        """List all JSON files"""
        try:
            files = []
            for f in os.listdir(self.base_path):
                if f.endswith('.json'):
                    files.append(f)
            return files
        except Exception as e:
            self.logger.error(f"Error listing files: {e}")
            return []
    
    async def cleanup_old_backups(self, max_backups: int = 10):
        """Clean up old backup files, keeping only the most recent ones"""
        try:
            backup_files = {}
            
            # Group backups by original filename
            for f in os.listdir(self.backup_path):
                if f.endswith('.json'):
                    # Extract original filename
                    parts = f.split('_')
                    if len(parts) >= 3:  # filename_date_time.json
                        original = '_'.join(parts[:-2]) + '.json'
                        if original not in backup_files:
                            backup_files[original] = []
                        backup_files[original].append(f)
            
            # Clean up each group
            for original, backups in backup_files.items():
                backups.sort(reverse=True)  # Newest first
                
                # Remove old backups
                for old_backup in backups[max_backups:]:
                    old_path = os.path.join(self.backup_path, old_backup)
                    os.remove(old_path)
                    self.logger.debug(f"Removed old backup: {old_backup}")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up backups: {e}")