from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn
import json
import asyncio
import subprocess
import os
import signal
import sys
import psutil
from typing import Dict, Optional
from session_manager import SessionManager
from logger import CustomLogger
from token_manager import TokenManager
from bot_process import BotProcess
from test_framework import TestFramework
from config_manager import ConfigManager

# Global variables
bot_processes: Dict[str, subprocess.Popen] = {}
bot_process_instance: Optional[BotProcess] = None
session_manager = SessionManager()
logger = CustomLogger()
token_manager = TokenManager()
config_manager = ConfigManager()

async def session_cleanup_task():
    """Background task to clean up expired sessions"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            await session_manager.cleanup_expired_sessions()
        except Exception as e:
            logger.error(f"Error in session cleanup task: {e}")

async def auto_start_bot():
    """Auto-start bot if configured"""
    try:
        token = await config_manager.get_discord_token()
        auto_start = await config_manager.get_auto_start()
        
        if token and auto_start and bot_process_instance:
            logger.info("Auto-starting bot with stored token...")
            success, message = await bot_process_instance.start_bot(token)
            if success:
                logger.info("Bot auto-started successfully")
            else:
                logger.error(f"Failed to auto-start bot: {message}")
    except Exception as e:
        logger.error(f"Error in auto-start: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global bot_process_instance
    
    # Startup
    logger.info("Starting gilf...")
    
    # Load configuration
    await config_manager.load_config()
    
    # Initialize bot process instance for in-process mode
    bot_process_instance = BotProcess()
    
    # Auto-start bot if configured
    await auto_start_bot()
    
    # Start session cleanup task
    cleanup_task = asyncio.create_task(session_cleanup_task())
    
    yield
    
    # Shutdown
    logger.info("Shutting down gilf...")
    
    # Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    # Stop all bot processes
    for process_id, process in bot_processes.items():
        try:
            if process.poll() is None:  # Process is still running
                process.terminate()
                process.wait(timeout=5)
        except Exception as e:
            logger.error(f"Error stopping bot process {process_id}: {e}")
    
    # Stop in-process bot
    if bot_process_instance:
        await bot_process_instance.stop_bot()

app = FastAPI(title="gilf", version="1.0.0", lifespan=lifespan)

# Serve static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")
if os.path.exists("templates"):
    app.mount("/templates", StaticFiles(directory="templates"), name="templates")

@app.get("/login")
async def login_page():
    """Serve the login page"""
    try:
        login_path = os.path.join("templates", "login.html")
        if os.path.exists(login_path):
            return FileResponse(login_path)
        else:
            raise HTTPException(status_code=404, detail="Login page not found")
    except Exception as e:
        logger.error(f"Error serving login page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/")
async def read_root():
    """Serve the main page"""
    try:
        # Serve the enhanced index.html
        index_path = os.path.join("templates", "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        else:
            raise HTTPException(status_code=404, detail="Index page not found")
    except Exception as e:
        logger.error(f"Error serving index page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "service": "gilf",
        "version": "1.0.0"
    })

@app.get("/api/bot/status")
async def get_bot_status():
    """Get current bot status"""
    try:
        if bot_process_instance:
            status = await bot_process_instance.get_bot_status()
            return JSONResponse(status)
        else:
            return JSONResponse({"error": "Bot process not initialized"})
    except Exception as e:
        logger.error(f"Error getting bot status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for bot communication"""
    session_id = None
    
    try:
        await websocket.accept()
        
        # Create session
        session_id = await session_manager.create_session()
        await session_manager.add_websocket_to_session(session_id, websocket)
        
        logger.info(f"WebSocket connected: {session_id}")
        
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "connected",
            "session_id": session_id,
            "message": "Connected to gilf"
        }))
        
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle message through bot process
                if bot_process_instance:
                    await bot_process_instance.handle_websocket_message(message, session_id)
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Bot process not initialized"
                    }))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Internal server error"
                }))
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up session
        if session_id:
            await session_manager.remove_websocket_from_session(session_id, websocket)
            # Optionally, you might not want to destroy the session on disconnect
            # await session_manager.destroy_session(session_id)

@app.post("/api/bot/start")
async def start_bot_api(request: dict = None):
    """REST API endpoint to start bot"""
    try:
        # Try to get token from request first, then from config
        token = None
        if request:
            token = request.get("token")
        
        if not token:
            # Get token from config
            token = await config_manager.get_discord_token()
            if not token:
                raise HTTPException(status_code=400, detail="No token configured. Please set a token first.")
        
        if not token_manager.validate_token_format(token):
            raise HTTPException(status_code=400, detail="Invalid token format")
        
        if bot_process_instance:
            result = await bot_process_instance.start_bot(token)
            if result["success"]:
                return JSONResponse({"message": result["message"]})
            else:
                raise HTTPException(status_code=400, detail=result["message"])
        else:
            raise HTTPException(status_code=500, detail="Bot process not initialized")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting bot via API: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/bot/stop")
async def stop_bot_api():
    """REST API endpoint to stop bot"""
    try:
        if bot_process_instance:
            await bot_process_instance.stop_bot()
            return JSONResponse({"message": "Bot stopped successfully"})
        else:
            raise HTTPException(status_code=500, detail="Bot process not initialized")
            
    except Exception as e:
        logger.error(f"Error stopping bot via API: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Configuration API endpoints
@app.get("/api/config")
async def get_config():
    """Get current configuration"""
    try:
        config = config_manager.get_config()
        # Remove sensitive data from response
        safe_config = config.copy()
        if "discord" in safe_config and "token" in safe_config["discord"]:
            safe_config["discord"]["token"] = "***" if safe_config["discord"]["token"] else ""
        return JSONResponse(safe_config)
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/config/token")
async def set_token(request: dict):
    """Set Discord token"""
    try:
        token = request.get("token")
        auto_start = request.get("auto_start", False)
        
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")
        
        if not token_manager.validate_token_format(token):
            raise HTTPException(status_code=400, detail="Invalid token format")
        
        # Store token and auto-start preference
        await config_manager.set_discord_token(token)
        await config_manager.set_auto_start(auto_start)
        
        return JSONResponse({"message": "Token saved successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/config/auto-start")
async def set_auto_start(request: dict):
    """Set auto-start preference"""
    try:
        enabled = request.get("enabled", False)
        await config_manager.set_auto_start(enabled)
        return JSONResponse({"message": f"Auto-start {'enabled' if enabled else 'disabled'}"})
    except Exception as e:
        logger.error(f"Error setting auto-start: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/config/feature")
async def set_feature_config(request: dict):
    """Set feature configuration"""
    try:
        feature = request.get("feature")
        config = request.get("config")
        
        if not feature or not config:
            raise HTTPException(status_code=400, detail="Feature and config are required")
        
        await config_manager.set_feature_config(feature, config)
        return JSONResponse({"message": f"Feature '{feature}' configured successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting feature config: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.delete("/api/config/token")
async def clear_token():
    """Clear stored Discord token"""
    try:
        await config_manager.clear_token()
        # Stop bot if running
        if bot_process_instance:
            await bot_process_instance.stop_bot()
        return JSONResponse({"message": "Token cleared successfully"})
    except Exception as e:
        logger.error(f"Error clearing token: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def start_separate_bot_process(token: str, session_id: str = None) -> str:
    """Start bot in a separate process"""
    try:
        import uuid
        process_id = str(uuid.uuid4())
        
        # Prepare command
        cmd = ["python3", "bot_process.py", token]
        if session_id:
            cmd.append(session_id)
        
        # Start process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd()
        )
        
        bot_processes[process_id] = process
        logger.info(f"Started bot process {process_id} with PID {process.pid}")
        
        return process_id
        
    except Exception as e:
        logger.error(f"Failed to start separate bot process: {e}")
        raise

def stop_bot_process(process_id: str) -> bool:
    """Stop a specific bot process"""
    try:
        if process_id not in bot_processes:
            return False
        
        process = bot_processes[process_id]
        
        if process.poll() is None:  # Process is still running
            # Try graceful shutdown first
            process.terminate()
            
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown fails
                process.kill()
                process.wait()
        
        del bot_processes[process_id]
        logger.info(f"Stopped bot process {process_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error stopping bot process {process_id}: {e}")
        return False

# Test framework instance
test_framework = TestFramework()

# Test API endpoints
@app.get("/test")
async def test_dashboard():
    """Serve the test dashboard"""
    return FileResponse("templates/test_dashboard.html")

@app.websocket("/ws/test")
async def test_websocket(websocket: WebSocket):
    """WebSocket endpoint for test updates"""
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "stop_tests":
                # Handle test stop request
                await websocket.send_text(json.dumps({
                    "type": "test_stopped",
                    "message": "Tests stopped by user request"
                }))
                break
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Test WebSocket error: {e}")

@app.post("/api/test/run-all")
async def run_all_tests():
    """Run all tests in the framework"""
    try:
        results = await test_framework.run_all_tests()
        return JSONResponse(results)
    except Exception as e:
        logger.error(f"Error running all tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/run-priority/{priority}")
async def run_priority_tests(priority: int):
    """Run tests for a specific priority level"""
    try:
        results = await test_framework.run_priority_tests(priority)
        return JSONResponse(results)
    except Exception as e:
        logger.error(f"Error running priority {priority} tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test/run-integration")
async def run_integration_tests():
    """Run integration tests"""
    try:
        results = await test_framework.run_integration_tests()
        return JSONResponse(results)
    except Exception as e:
        logger.error(f"Error running integration tests: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/status")
async def get_test_status():
    """Get current test execution status"""
    try:
        status = test_framework.get_test_status()
        return JSONResponse(status)
    except Exception as e:
        logger.error(f"Error getting test status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/test/results")
async def get_test_results():
    """Get latest test results"""
    try:
        results = test_framework.get_latest_results()
        return JSONResponse(results)
    except Exception as e:
        logger.error(f"Error getting test results: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Global shutdown flag
shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global shutdown_requested
    
    if shutdown_requested:
        logger.warning("Shutdown already in progress, forcing exit...")
        sys.exit(1)
    
    shutdown_requested = True
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    
    # Stop all bot processes
    for process_id, process in list(bot_processes.items()):
        try:
            if process.poll() is None:
                logger.info(f"Terminating bot process {process_id}")
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    logger.warning(f"Force killing bot process {process_id}")
                    process.kill()
                    process.wait()
        except Exception as e:
            logger.error(f"Error stopping bot process {process_id}: {e}")
    
    # Clear the processes dict
    bot_processes.clear()
    
    # Stop in-process bot synchronously
    if bot_process_instance:
        try:
            # Force synchronous shutdown
            bot_process_instance.running = False
            if bot_process_instance.bot:
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(bot_process_instance.bot.close())
                    loop.close()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error stopping bot instance: {e}")
    
    logger.info("Shutdown complete")
    sys.exit(0)

if __name__ == "__main__":
    import argparse
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(description="gilf")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument("--log-level", default="info", help="Log level")
    
    args = parser.parse_args()
    
    logger.info(f"Starting web server on {args.host}:{args.port}")
    
    try:
        uvicorn.run(
            "main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level
        )
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        logger.info("Server stopped")