import os
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import getpass
import aiofiles

class TokenManager:
    def __init__(self, storage_path="data/json/tokens.enc"):
        self.storage_path = storage_path
        self.key = None
        self.fernet = None
        
    def _generate_key(self, password: str, salt: bytes = None) -> bytes:
        """Generate encryption key from password"""
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt
    
    def setup_encryption(self, password: str = None):
        """Setup encryption with password"""
        if password is None:
            password = getpass.getpass("Enter master password for token encryption: ")
        
        # Check if salt file exists
        salt_path = "data/json/salt.key"
        if os.path.exists(salt_path):
            with open(salt_path, 'rb') as f:
                salt = f.read()
        else:
            os.makedirs(os.path.dirname(salt_path), exist_ok=True)
            salt = os.urandom(16)
            with open(salt_path, 'wb') as f:
                f.write(salt)
        
        self.key, _ = self._generate_key(password, salt)
        self.fernet = Fernet(self.key)
        return True
    
    async def store_token(self, token: str, token_name: str = "main"):
        """Store encrypted token"""
        if not self.fernet:
            raise ValueError("Encryption not setup. Call setup_encryption() first.")
        
        # Load existing tokens
        tokens = await self.load_tokens()
        
        # Encrypt and store new token
        encrypted_token = self.fernet.encrypt(token.encode())
        tokens[token_name] = base64.b64encode(encrypted_token).decode()
        
        # Save to file
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        async with aiofiles.open(self.storage_path, 'w') as f:
            await f.write(json.dumps(tokens, indent=2))
        
        return True
    
    async def load_tokens(self) -> dict:
        """Load and decrypt all tokens"""
        if not os.path.exists(self.storage_path):
            return {}
        
        async with aiofiles.open(self.storage_path, 'r') as f:
            encrypted_tokens = json.loads(await f.read())
        
        return encrypted_tokens
    
    async def get_token(self, token_name: str = "main") -> str:
        """Get decrypted token"""
        if not self.fernet:
            raise ValueError("Encryption not setup. Call setup_encryption() first.")
        
        tokens = await self.load_tokens()
        if token_name not in tokens:
            raise KeyError(f"Token '{token_name}' not found")
        
        encrypted_token = base64.b64decode(tokens[token_name])
        decrypted_token = self.fernet.decrypt(encrypted_token)
        return decrypted_token.decode()
    
    async def delete_token(self, token_name: str):
        """Delete a stored token"""
        tokens = await self.load_tokens()
        if token_name in tokens:
            del tokens[token_name]
            async with aiofiles.open(self.storage_path, 'w') as f:
                await f.write(json.dumps(tokens, indent=2))
        return True
    
    async def list_tokens(self) -> list:
        """List all stored token names"""
        tokens = await self.load_tokens()
        return list(tokens.keys())
    
    def validate_token_format(self, token: str) -> bool:
        """Basic token format validation"""
        # Discord tokens are typically 59-68 characters
        if len(token) < 50 or len(token) > 100:
            return False
        
        # Should contain base64-like characters
        import re
        pattern = r'^[A-Za-z0-9._-]+$'
        return bool(re.match(pattern, token))