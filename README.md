# WebSocket Notification Server with Graceful Shutdown

FastAPI WebSocket server that supports real-time notifications with intelligent graceful shutdown mechanisms.

## Setup Instructions

### 1. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Server

**Single Worker:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Multiple Workers:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Testing the WebSocket Endpoint

### Method 1: Built-in Web Client

1. Start the server
2. Open browser: `http://localhost:8000`
3. Click "Connect" to establish WebSocket connection
4. Observe periodic notifications every 10 seconds

### Method 2: Using `websocat` (CLI)

Install websocat

macOS: brew install websocat

Linux: cargo install websocat

```bash
websocat ws://localhost:8000/ws
```

### Method 3: Python Client

```python
import asyncio
import websockets
import json

async def test_client():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        print("Connected to server")
        
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            print(f"Received: {data}")

asyncio.run(test_client())
```

## API Endpoints

### WebSocket Endpoint
- **URL**: `ws://localhost:8000/ws`
- **Description**: Main WebSocket endpoint for real-time notifications

## Graceful Shutdown Logic

### How It Works

1. **Signal Reception**: Server catches SIGTERM or SIGINT signals
2. **Shutdown Initiation**: 
   - Stops accepting new connections
   - Cancels background notification task
   - Starts monitoring active connections
3. **Wait Phase**: 
   - Monitors active connection count every 5 seconds
   - Logs remaining time and connection count
4. **Completion**:
   - **Normal**: All connections closed → immediate shutdown
   - **Timeout**: 30 minutes elapsed → forced shutdown

### Multi-Worker Handling

When running with multiple uvicorn workers:

- Each worker process runs independently
- Each maintains its own connection pool
- Signal handlers work per-process
- Graceful shutdown applies to each worker individually

**Important**: When using `--workers N`:
- Each worker handles its own WebSocket connections
- Shutdown timeout applies per-worker (not globally)
- Load balancing happens at the OS level

### Testing Graceful Shutdown

#### Single Worker Test:
```bash
# Terminal 1: Start server
uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Connect clients
python test_client.py  # Or use web UI

# Terminal 1: Send shutdown signal
# Press Ctrl+C (SIGINT) or: kill -SIGTERM <pid>

# Observe logs:
# - "Shutdown signal received"
# - "Waiting for X connections to close. Time remaining: XXXXs"
# - "All WebSocket connections closed. Proceeding with shutdown."
```

#### Multi-Worker Test:
```bash
# Start with multiple workers
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Connect multiple clients
# Send shutdown signal
# Each worker shuts down independently
```

### Shutdown Scenarios

#### Scenario 1: All Connections Close Quickly
```
[INFO] Shutdown signal received
[INFO] Graceful shutdown initiated
[INFO] Waiting for 3 connections to close. Time remaining: 1800s
[INFO] Client disconnected. Total connections: 2
[INFO] Waiting for 2 connections to close. Time remaining: 1795s
[INFO] Client disconnected. Total connections: 1
[INFO] Client disconnected. Total connections: 0
[INFO] All WebSocket connections closed. Proceeding with shutdown.
[INFO] Server shutdown complete
```

#### Scenario 2: Timeout Reached
```
[INFO] Shutdown signal received
[INFO] Graceful shutdown initiated
[INFO] Waiting for 5 connections to close. Time remaining: 1800s
...
[INFO] Waiting for 2 connections to close. Time remaining: 10s
[WARNING] Shutdown timeout (30 minutes) reached. Forcing shutdown with 2 active connections.
[INFO] Server shutdown complete
```
