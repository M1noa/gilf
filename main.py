from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
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
from session_manager import get_session_manager
from logger import get_logger
from token_manager import TokenManager
from bot_process import BotProcess

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global bot_process_instance
    
    # Startup
    logger.info("Starting Discord Self-Bot Manager...")
    
    # Initialize bot process instance for in-process mode
    bot_process_instance = BotProcess()
    
    # Start session cleanup task
    cleanup_task = asyncio.create_task(session_cleanup_task())
    
    yield
    
    # Shutdown
    logger.info("Shutting down Discord Self-Bot Manager...")
    
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

app = FastAPI(title="Discord Self-Bot Manager", version="1.0.0", lifespan=lifespan)
logger = get_logger()
session_manager = get_session_manager()
token_manager = TokenManager()

# Bot process management
bot_processes: Dict[str, subprocess.Popen] = {}
bot_process_instance: Optional[BotProcess] = None

# Serve static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")



async def session_cleanup_task():
    """Background task to clean up expired sessions"""
    while True:
        try:
            await session_manager.cleanup_expired_sessions()
            await asyncio.sleep(300)  # Clean up every 5 minutes
        except Exception as e:
            logger.error(f"Error in session cleanup task: {e}")
            await asyncio.sleep(60)  # Retry after 1 minute on error

@app.get("/")
async def get_index():
    """Serve the main web interface"""
    try:
        if os.path.exists("index.html"):
            with open("index.html", "r", encoding="utf-8") as f:
                html_content = f.read()
            return HTMLResponse(content=html_content, status_code=200)
        else:
            # Return a basic HTML page if index.html doesn't exist
            basic_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Discord Self-Bot Manager</title>
                <meta charset="utf-8">
            </head>
            <body>
                <h1>Discord Self-Bot Manager</h1>
                <p>Web interface is not yet implemented. Please use the WebSocket API.</p>
                <p>WebSocket endpoint: ws://localhost:8000/ws</p>
            </body>
            </html>
            """
            return HTMLResponse(content=basic_html, status_code=200)
    except Exception as e:
        logger.error(f"Error serving index page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "service": "Discord Self-Bot Manager",
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
        await session_manager.add_websocket(session_id, websocket)
        
        logger.info(f"WebSocket connected: {session_id}")
        
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "connected",
            "session_id": session_id,
            "message": "Connected to Discord Self-Bot Manager"
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
            await session_manager.remove_websocket(session_id, websocket)
            await session_manager.destroy_session(session_id)

@app.post("/api/bot/start")
async def start_bot_api(request: dict):
    """REST API endpoint to start bot"""
    try:
        token = request.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token is required")
        
        if not token_manager.validate_token_format(token):
            raise HTTPException(status_code=400, detail="Invalid token format")
        
        if bot_process_instance:
            success = await bot_process_instance.start_bot(token)
            if success:
                return JSONResponse({"message": "Bot started successfully"})
            else:
                raise HTTPException(status_code=500, detail="Failed to start bot")
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
    
    parser = argparse.ArgumentParser(description="Discord Self-Bot Manager")
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