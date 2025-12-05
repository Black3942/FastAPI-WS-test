import asyncio
import signal
import logging

from datetime import datetime, timedelta
from typing import Set
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        if not self.active_connections:
            logger.debug("No active connections to broadcast to")
            return
        
        disconnected = set()
        async with self._lock:
            connections = self.active_connections.copy()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.add(connection)

        if disconnected:
            async with self._lock:
                self.active_connections -= disconnected
    
    @property
    def connection_count(self) -> int:
        return len(self.active_connections)


class GracefulShutdownManager:
    def __init__(self, manager: ConnectionManager, timeout_minutes: int = 30):
        self.manager = manager
        self.timeout_minutes = timeout_minutes
        self.shutdown_initiated = False
        self.shutdown_event = asyncio.Event()
    
    async def wait_for_shutdown(self):
        if not self.shutdown_initiated:
            return
        
        logger.info("Graceful shutdown initiated")
        start_time = datetime.now()
        timeout = timedelta(minutes=self.timeout_minutes)
        
        while True:
            connection_count = self.manager.connection_count
            elapsed = datetime.now() - start_time
            remaining = timeout - elapsed
            
            if connection_count == 0:
                logger.info("All WebSocket connections closed. Proceeding with shutdown.")
                break
            
            if elapsed >= timeout:
                logger.warning(
                    f"Shutdown timeout ({self.timeout_minutes} minutes) reached. "
                    f"Forcing shutdown with {connection_count} active connections."
                )
                break
            
            logger.info(
                f"Waiting for {connection_count} connections to close. "
                f"Time remaining: {remaining.total_seconds():.0f}s"
            )
            await asyncio.sleep(5)
        
        self.shutdown_event.set()
    
    def initiate_shutdown(self):
        self.shutdown_initiated = True
        logger.info("Shutdown signal received")


connection_manager = ConnectionManager()
shutdown_manager = GracefulShutdownManager(connection_manager)


async def notification_broadcaster():
    counter = 0
    while not shutdown_manager.shutdown_initiated:
        try:
            await asyncio.sleep(10)
            counter += 1
            message = {
                "type": "notification",
                "message": f"Periodic notification #{counter}",
                "timestamp": datetime.now().isoformat(),
                "active_connections": connection_manager.connection_count
            }
            await connection_manager.broadcast(message)
            logger.debug(f"Broadcast notification #{counter}")
        except asyncio.CancelledError:
            logger.info("Notification broadcaster cancelled")
            break
        except Exception as e:
            logger.error(f"Error in notification broadcaster: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WebSocket server")
    broadcaster_task = asyncio.create_task(notification_broadcaster())

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        shutdown_manager.initiate_shutdown()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    yield

    logger.info("Initiating shutdown sequence")
    shutdown_manager.initiate_shutdown()
    broadcaster_task.cancel()

    try:
        await broadcaster_task
    except asyncio.CancelledError:
        pass

    await shutdown_manager.wait_for_shutdown()
    logger.info("Server shutdown complete")


app = FastAPI(title="WebSocket Notification Server", lifespan=lifespan)


@app.get("/")
async def get():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Test Client</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            #messages { border: 1px solid #ccc; height: 400px; overflow-y: scroll; padding: 10px; margin: 20px 0; }
            .message { margin: 5px 0; padding: 5px; background: #f0f0f0; border-radius: 3px; }
            button { padding: 10px 20px; margin: 5px; font-size: 16px; cursor: pointer; }
            .connected { color: green; }
            .disconnected { color: red; }
        </style>
    </head>
    <body>
        <h1>WebSocket Test Client</h1>
        <p>Status: <span id="status" class="disconnected">Disconnected</span></p>
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
        <button onclick="clearMessages()">Clear Messages</button>
        <div id="messages"></div>
        
        <script>
            let ws = null;
            
            function connect() {
                if (ws) {
                    console.log("Already connected");
                    return;
                }
                
                ws = new WebSocket("ws://localhost:8000/ws");
                
                ws.onopen = function(event) {
                    document.getElementById("status").textContent = "Connected";
                    document.getElementById("status").className = "connected";
                    addMessage("Connected to server", "system");
                };
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    addMessage(JSON.stringify(data, null, 2), "notification");
                };
                
                ws.onerror = function(error) {
                    addMessage("WebSocket error: " + error, "error");
                };
                
                ws.onclose = function(event) {
                    document.getElementById("status").textContent = "Disconnected";
                    document.getElementById("status").className = "disconnected";
                    addMessage("Disconnected from server", "system");
                    ws = null;
                };
            }
            
            function disconnect() {
                if (ws) {
                    ws.close();
                    ws = null;
                }
            }
            
            function addMessage(message, type) {
                const messagesDiv = document.getElementById("messages");
                const messageDiv = document.createElement("div");
                messageDiv.className = "message";
                messageDiv.innerHTML = `<strong>${new Date().toLocaleTimeString()}</strong> [${type}]: <pre>${message}</pre>`;
                messagesDiv.appendChild(messageDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
            
            function clearMessages() {
                document.getElementById("messages").innerHTML = "";
            }
            
            // Auto-connect on page load
            window.addEventListener("load", connect);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(html)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await connection_manager.connect(websocket)
    
    try:
        await websocket.send_json({
            "type": "welcome",
            "message": "Connected to WebSocket server",
            "timestamp": datetime.now().isoformat()
        })

        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
                logger.debug(f"Received from client: {data}")

                await websocket.send_json({
                    "type": "echo",
                    "message": f"Server received: {data}",
                    "timestamp": datetime.now().isoformat()
                })
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.now().isoformat()
                })
    
    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await connection_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
