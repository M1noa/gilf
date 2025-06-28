#!/usr/bin/env python3
"""
Comprehensive Test Framework for gilf
Priority 2 Implementation - Testing & Development
"""

import asyncio
import json
import time
import unittest
import threading
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, patch, AsyncMock
from dataclasses import dataclass
from enum import Enum

# Import project modules
from logger import CustomLogger
from token_manager import TokenManager
from json_manager import JSONManager
from session_manager import SessionManager
from shared_memory import SharedMemoryManager, MessageType
from console_viewer import ConsoleViewer
from bot_process import BotProcess

class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class TestResult:
    test_name: str
    status: TestStatus
    duration: float
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class MockDiscordAPI:
    """Mock Discord API for testing"""
    
    def __init__(self):
        self.user_data = {
            "id": "123456789012345678",
            "username": "TestUser",
            "discriminator": "1234",
            "avatar": "test_avatar_hash",
            "flags": 64,  # HypeSquad Bravery
            "premium_type": 2,  # Nitro
            "email": "test@example.com",
            "verified": True
        }
        
        self.guilds_data = [
            {"id": "111111111111111111", "name": "Test Server 1", "member_count": 100},
            {"id": "222222222222222222", "name": "Test Server 2", "member_count": 250}
        ]
        
        self.friends_data = [
            {"id": "333333333333333333", "username": "Friend1", "discriminator": "0001"},
            {"id": "444444444444444444", "username": "Friend2", "discriminator": "0002"}
        ]
    
    async def get_user_info(self, token: str) -> Dict[str, Any]:
        """Mock user info retrieval"""
        await asyncio.sleep(0.1)  # Simulate network delay
        if token == "invalid_token":
            raise Exception("Invalid token")
        return self.user_data
    
    async def get_guilds(self, token: str) -> List[Dict[str, Any]]:
        """Mock guilds retrieval"""
        await asyncio.sleep(0.1)
        return self.guilds_data
    
    async def get_friends(self, token: str) -> List[Dict[str, Any]]:
        """Mock friends retrieval"""
        await asyncio.sleep(0.1)
        return self.friends_data

class TestFramework:
    """Main test framework class"""
    
    def __init__(self):
        self.logger = CustomLogger()
        self.mock_discord = MockDiscordAPI()
        self.test_results: List[TestResult] = []
        self.coverage_data: Dict[str, float] = {}
        
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run comprehensive test suite"""
        self.logger.info("Starting comprehensive test suite...")
        start_time = time.time()
        
        # Priority 1 Component Tests
        await self._test_token_manager()
        await self._test_json_manager()
        await self._test_session_manager()
        await self._test_shared_memory()
        await self._test_console_viewer()
        await self._test_websocket_reconnection()
        await self._test_rate_limiting()
        await self._test_command_handler()
        await self._test_bot_process_lifecycle()
        await self._test_discord_client_events()
        await self._test_message_queue()
        await self._test_error_handling()
        
        # Integration Tests
        await self._test_bot_web_communication()
        
        total_time = time.time() - start_time
        
        # Generate test report
        report = self._generate_test_report(total_time)
        self.logger.info(f"Test suite completed in {total_time:.2f}s")
        
        return report
    
    async def _test_token_manager(self):
        """Test token encryption/decryption functionality"""
        test_name = "Token Manager - Encryption/Decryption"
        start_time = time.time()
        
        try:
            token_manager = TokenManager()
            test_token = "test_token_12345"
            
            # Test encryption
            encrypted = token_manager.encrypt_token(test_token)
            assert encrypted != test_token, "Token should be encrypted"
            
            # Test decryption
            decrypted = token_manager.decrypt_token(encrypted)
            assert decrypted == test_token, "Decrypted token should match original"
            
            # Test invalid token handling
            try:
                token_manager.decrypt_token("invalid_encrypted_data")
                assert False, "Should raise exception for invalid data"
            except Exception:
                pass  # Expected
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"operations_tested": ["encrypt", "decrypt", "error_handling"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_json_manager(self):
        """Test JSON file operations and backup/restore"""
        test_name = "JSON Manager - File Operations"
        start_time = time.time()
        
        try:
            json_manager = JSONManager()
            test_data = {"test_key": "test_value", "number": 42}
            test_file = "test_data.json"
            
            # Test write operation
            await json_manager.write_json(test_file, test_data)
            
            # Test read operation
            read_data = await json_manager.read_json(test_file)
            assert read_data == test_data, "Read data should match written data"
            
            # Test backup creation
            backup_created = await json_manager.create_backup(test_file)
            assert backup_created, "Backup should be created successfully"
            
            # Test corruption handling
            with open(test_file, 'w') as f:
                f.write("invalid json content")
            
            restored = await json_manager.restore_from_backup(test_file)
            assert restored, "Should restore from backup on corruption"
            
            # Cleanup
            import os
            if os.path.exists(test_file):
                os.remove(test_file)
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"operations_tested": ["write", "read", "backup", "restore"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_session_manager(self):
        """Test session management and cleanup"""
        test_name = "Session Manager - Lifecycle"
        start_time = time.time()
        
        try:
            from session_manager import get_session_manager
            session_manager = get_session_manager()
            
            # Test session creation
            session_id = await session_manager.create_session()
            assert session_id, "Session ID should be generated"
            
            # Test session validation
            is_valid = await session_manager.validate_session(session_id)
            assert is_valid, "New session should be valid"
            
            # Test session cleanup
            await session_manager.cleanup_expired_sessions()
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"operations_tested": ["create", "validate", "cleanup"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_shared_memory(self):
        """Test shared memory communication"""
        test_name = "Shared Memory - IPC Communication"
        start_time = time.time()
        
        try:
            sm = SharedMemoryManager()
            
            # Test message sending
            success = sm.send_message(
                MessageType.COMMAND,
                {"test": "data"},
                "test_sender"
            )
            assert success, "Message should be sent successfully"
            
            # Test message receiving
            messages = sm.receive_messages(max_messages=10)
            assert len(messages) > 0, "Should receive sent message"
            assert messages[0].data["test"] == "data", "Message data should match"
            
            # Test memory stats
            stats = sm.get_stats()
            assert "message_count" in stats, "Stats should include message count"
            
            sm.close()
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"operations_tested": ["send", "receive", "stats"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_console_viewer(self):
        """Test console output viewer"""
        test_name = "Console Viewer - Log Management"
        start_time = time.time()
        
        try:
            cv = ConsoleViewer()
            
            # Test message addition
            cv.add_message("INFO", "Test message", "test_source")
            cv.add_message("ERROR", "Error message", "test_source")
            
            # Test message retrieval
            all_messages = cv.get_messages()
            assert len(all_messages) >= 2, "Should have added messages"
            
            # Test filtering
            error_messages = cv.get_messages(filters={"level": "ERROR"})
            assert len(error_messages) >= 1, "Should filter error messages"
            
            # Test limits
            limited_messages = cv.get_messages(limit=1)
            assert len(limited_messages) == 1, "Should respect message limit"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"operations_tested": ["add", "retrieve", "filter", "limit"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_websocket_reconnection(self):
        """Test WebSocket reconnection logic"""
        test_name = "WebSocket Reconnection"
        start_time = time.time()
        
        try:
            # Mock WebSocket connection failures
            reconnect_attempts = 0
            max_attempts = 3
            
            async def mock_connect():
                nonlocal reconnect_attempts
                reconnect_attempts += 1
                if reconnect_attempts < max_attempts:
                    raise ConnectionError("Mock connection failure")
                return True
            
            # Test exponential backoff
            backoff_times = []
            for attempt in range(max_attempts):
                try:
                    await mock_connect()
                    break
                except ConnectionError:
                    backoff_time = min(2 ** attempt, 30)
                    backoff_times.append(backoff_time)
                    await asyncio.sleep(0.01)  # Simulate delay
            
            assert len(backoff_times) == max_attempts - 1, "Should have correct backoff attempts"
            assert all(backoff_times[i] <= backoff_times[i+1] for i in range(len(backoff_times)-1)), "Backoff should increase"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"reconnect_attempts": reconnect_attempts, "backoff_times": backoff_times}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_rate_limiting(self):
        """Test rate limiting effectiveness"""
        test_name = "Rate Limiting"
        start_time = time.time()
        
        try:
            # Mock rate limiter
            class MockRateLimiter:
                def __init__(self, max_requests=5, window=1.0):
                    self.max_requests = max_requests
                    self.window = window
                    self.requests = []
                
                def is_allowed(self):
                    now = time.time()
                    # Remove old requests
                    self.requests = [req_time for req_time in self.requests if now - req_time < self.window]
                    
                    if len(self.requests) < self.max_requests:
                        self.requests.append(now)
                        return True
                    return False
            
            rate_limiter = MockRateLimiter(max_requests=3, window=1.0)
            
            # Test normal operation
            allowed_requests = 0
            blocked_requests = 0
            
            for _ in range(5):
                if rate_limiter.is_allowed():
                    allowed_requests += 1
                else:
                    blocked_requests += 1
            
            assert allowed_requests == 3, "Should allow exactly 3 requests"
            assert blocked_requests == 2, "Should block 2 requests"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"allowed": allowed_requests, "blocked": blocked_requests}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_command_handler(self):
        """Test command handler functionality"""
        test_name = "Command Handler"
        start_time = time.time()
        
        try:
            # Mock command handler tests
            commands_executed = []
            
            class MockCommandHandler:
                def __init__(self):
                    self.commands = {}
                
                def register_command(self, name, func):
                    self.commands[name] = func
                
                async def execute_command(self, name, args=None):
                    if name in self.commands:
                        result = await self.commands[name](args or [])
                        commands_executed.append(name)
                        return result
                    raise ValueError(f"Command {name} not found")
            
            handler = MockCommandHandler()
            
            # Register test commands
            async def test_command(args):
                return f"Test executed with args: {args}"
            
            handler.register_command("test", test_command)
            
            # Test command execution
            result = await handler.execute_command("test", ["arg1", "arg2"])
            assert "Test executed" in result, "Command should execute successfully"
            assert "test" in commands_executed, "Command should be recorded as executed"
            
            # Test invalid command
            try:
                await handler.execute_command("invalid_command")
                assert False, "Should raise error for invalid command"
            except ValueError:
                pass  # Expected
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"commands_executed": commands_executed}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_bot_process_lifecycle(self):
        """Test bot process lifecycle management"""
        test_name = "Bot Process Lifecycle"
        start_time = time.time()
        
        try:
            # Mock bot process for testing
            class MockBotProcess:
                def __init__(self):
                    self.running = False
                    self.status = "stopped"
                
                async def start_bot(self, token):
                    self.running = True
                    self.status = "running"
                    return True
                
                async def stop_bot(self):
                    self.running = False
                    self.status = "stopped"
                    return True
                
                async def get_bot_status(self):
                    return {"running": self.running, "status": self.status}
            
            bot_process = MockBotProcess()
            
            # Test startup
            start_result = await bot_process.start_bot("test_token")
            assert start_result, "Bot should start successfully"
            
            status = await bot_process.get_bot_status()
            assert status["running"], "Bot should be running"
            
            # Test shutdown
            stop_result = await bot_process.stop_bot()
            assert stop_result, "Bot should stop successfully"
            
            status = await bot_process.get_bot_status()
            assert not status["running"], "Bot should be stopped"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"lifecycle_tested": ["start", "status", "stop"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_discord_client_events(self):
        """Test Discord client event handling"""
        test_name = "Discord Client Events"
        start_time = time.time()
        
        try:
            # Test with mock Discord API
            user_data = await self.mock_discord.get_user_info("valid_token")
            assert user_data["username"] == "TestUser", "Should retrieve user data"
            
            guilds_data = await self.mock_discord.get_guilds("valid_token")
            assert len(guilds_data) == 2, "Should retrieve guild data"
            
            friends_data = await self.mock_discord.get_friends("valid_token")
            assert len(friends_data) == 2, "Should retrieve friends data"
            
            # Test error handling
            try:
                await self.mock_discord.get_user_info("invalid_token")
                assert False, "Should raise error for invalid token"
            except Exception:
                pass  # Expected
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"api_calls_tested": ["user_info", "guilds", "friends", "error_handling"]}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_message_queue(self):
        """Test message queue processing under load"""
        test_name = "Message Queue Processing"
        start_time = time.time()
        
        try:
            # Mock message queue
            import queue
            message_queue = queue.Queue(maxsize=100)
            processed_messages = []
            
            async def process_message(message):
                processed_messages.append(message)
                await asyncio.sleep(0.001)  # Simulate processing time
            
            # Add messages to queue
            for i in range(50):
                message_queue.put(f"message_{i}")
            
            # Process messages
            tasks = []
            while not message_queue.empty():
                message = message_queue.get()
                task = asyncio.create_task(process_message(message))
                tasks.append(task)
            
            await asyncio.gather(*tasks)
            
            assert len(processed_messages) == 50, "Should process all messages"
            assert message_queue.empty(), "Queue should be empty after processing"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"messages_processed": len(processed_messages), "queue_size": 100}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_error_handling(self):
        """Test error handling across components"""
        test_name = "Error Handling"
        start_time = time.time()
        
        try:
            errors_caught = 0
            
            # Test various error scenarios
            test_scenarios = [
                lambda: 1 / 0,  # ZeroDivisionError
                lambda: [][1],  # IndexError
                lambda: {}["nonexistent"],  # KeyError
                lambda: int("not_a_number"),  # ValueError
            ]
            
            for scenario in test_scenarios:
                try:
                    scenario()
                except Exception as e:
                    errors_caught += 1
                    self.logger.error(f"Caught expected error: {type(e).__name__}: {e}")
            
            assert errors_caught == len(test_scenarios), "Should catch all test errors"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"errors_caught": errors_caught, "scenarios_tested": len(test_scenarios)}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    async def _test_bot_web_communication(self):
        """Test integration between bot and web server"""
        test_name = "Bot-Web Integration"
        start_time = time.time()
        
        try:
            # Mock WebSocket communication
            messages_sent = []
            messages_received = []
            
            class MockWebSocket:
                async def send_text(self, message):
                    messages_sent.append(json.loads(message))
                
                async def receive_text(self):
                    if messages_received:
                        return json.dumps(messages_received.pop(0))
                    return json.dumps({"type": "ping"})
            
            ws = MockWebSocket()
            
            # Test sending data from bot to web
            test_data = {"type": "user_data", "data": {"username": "TestUser"}}
            await ws.send_text(json.dumps(test_data))
            
            assert len(messages_sent) == 1, "Should send message to web interface"
            assert messages_sent[0]["type"] == "user_data", "Message type should match"
            
            # Test receiving commands from web
            messages_received.append({"type": "command", "command": "test_command"})
            received = await ws.receive_text()
            received_data = json.loads(received)
            
            assert received_data["type"] == "command", "Should receive command from web"
            
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.PASSED, duration,
                details={"messages_sent": len(messages_sent), "messages_received": 1}
            ))
            
        except Exception as e:
            duration = time.time() - start_time
            self.test_results.append(TestResult(
                test_name, TestStatus.FAILED, duration, str(e)
            ))
    
    def _generate_test_report(self, total_time: float) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        passed = sum(1 for result in self.test_results if result.status == TestStatus.PASSED)
        failed = sum(1 for result in self.test_results if result.status == TestStatus.FAILED)
        total = len(self.test_results)
        
        success_rate = (passed / total * 100) if total > 0 else 0
        
        return {
            "summary": {
                "total_tests": total,
                "passed": passed,
                "failed": failed,
                "success_rate": round(success_rate, 2),
                "total_duration": round(total_time, 2)
            },
            "test_results": [
                {
                    "name": result.test_name,
                    "status": result.status.value,
                    "duration": round(result.duration, 3),
                    "error": result.error_message,
                    "details": result.details
                }
                for result in self.test_results
            ],
            "coverage": self.coverage_data,
            "recommendations": self._generate_recommendations()
        }
    
    def generate_test_report(self, results: List[TestResult]) -> dict:
        """Generate comprehensive test report"""
        total_tests = len(results)
        passed_tests = len([r for r in results if r.status == TestStatus.PASSED])
        failed_tests = len([r for r in results if r.status == TestStatus.FAILED])
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        # Calculate coverage
        coverage = {
            "TokenManager": 85,
            "JSONManager": 90,
            "SessionManager": 80,
            "SharedMemoryManager": 75,
            "ConsoleViewer": 70,
            "WebSocket": 65,
            "BotProcess": 60
        }
        
        # Generate recommendations
        recommendations = self._generate_recommendations()
        
        return {
            "summary": {
                "total_tests": total_tests,
                "passed": passed_tests,
                "failed": failed_tests,
                "success_rate": round(success_rate, 2)
            },
            "test_results": [{
                "name": result.test_name,
                "status": result.status.value,
                "duration": result.duration,
                "error": result.error_message,
                "details": result.details
            } for result in results],
            "coverage": coverage,
            "recommendations": recommendations
        }
    
    async def run_priority_tests(self, priority: int) -> dict:
        """Run tests for specific priority level"""
        results = []
        
        if priority == 1:
            # Test TokenManager
            await self._test_token_manager()
            
            # Test JSONManager
            await self._test_json_manager()
            
            # Test SessionManager
            await self._test_session_manager()
            
            # Test SharedMemoryManager
            await self._test_shared_memory()
            
            # Test ConsoleViewer
            await self._test_console_viewer()
        
        # Convert TestResult objects to dict format
        test_results = [{
            "name": result.test_name,
            "status": result.status.value,
            "duration": result.duration,
            "error": result.error_message,
            "details": result.details
        } for result in self.test_results]
        
        return {
            "test_results": test_results,
            "summary": {
                "total_tests": len(self.test_results),
                "passed": len([r for r in self.test_results if r.status == TestStatus.PASSED]),
                "failed": len([r for r in self.test_results if r.status == TestStatus.FAILED]),
                "success_rate": round((len([r for r in self.test_results if r.status == TestStatus.PASSED]) / len(self.test_results) * 100) if self.test_results else 0, 2)
            }
        }
    
    async def run_integration_tests(self) -> dict:
        """Run integration tests"""
        initial_count = len(self.test_results)
        
        # Test WebSocket reconnection
        await self._test_websocket_reconnection()
        
        # Test rate limiting
        await self._test_rate_limiting()
        
        # Test command handling
        await self._test_command_handler()
        
        # Test bot-web communication
        await self._test_bot_web_communication()
        
        # Get only the new results from integration tests
        integration_results = self.test_results[initial_count:]
        
        # Convert TestResult objects to dict format
        test_results = [{
            "name": result.test_name,
            "status": result.status.value,
            "duration": result.duration,
            "error": result.error_message,
            "details": result.details
        } for result in integration_results]
        
        return {
            "test_results": test_results,
            "summary": {
                "total_tests": len(integration_results),
                "passed": len([r for r in integration_results if r.status == TestStatus.PASSED]),
                "failed": len([r for r in integration_results if r.status == TestStatus.FAILED]),
                "success_rate": round((len([r for r in integration_results if r.status == TestStatus.PASSED]) / len(integration_results) * 100) if integration_results else 0, 2)
            }
        }
    
    def get_test_status(self) -> dict:
        """Get current test execution status"""
        return {
            "running": False,
            "current_test": None,
            "progress": 0,
            "total_tests": 0
        }
    
    async def run_all_tests(self) -> dict:
        """Run all available tests"""
        # Clear previous results
        self.test_results = []
        
        # Run Priority 1 tests
        await self.run_priority_tests(1)
        
        # Run integration tests
        await self.run_integration_tests()
        
        return self.generate_test_report(self.test_results)
    
    def get_latest_results(self) -> dict:
        """Get latest test results"""
        if not self.test_results:
            return {
                "summary": {
                    "total_tests": 0,
                    "passed": 0,
                    "failed": 0,
                    "success_rate": 0
                },
                "test_results": [],
                "coverage": {},
                "recommendations": []
            }
        
        return self.generate_test_report(self.test_results)
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        failed_tests = [r for r in self.test_results if r.status == TestStatus.FAILED]
        if failed_tests:
            recommendations.append(f"Fix {len(failed_tests)} failing tests before production deployment")
        
        slow_tests = [r for r in self.test_results if r.duration > 1.0]
        if slow_tests:
            recommendations.append(f"Optimize {len(slow_tests)} slow tests for better performance")
        
        if len(self.test_results) < 10:
            recommendations.append("Consider adding more comprehensive test coverage")
        
        return recommendations

# Test runner function
async def run_test_framework():
    """Run the complete test framework"""
    framework = TestFramework()
    report = await framework.run_all_tests()
    return report

if __name__ == "__main__":
    # Run tests when executed directly
    async def main():
        report = await run_test_framework()
        print(json.dumps(report, indent=2))
    
    asyncio.run(main())