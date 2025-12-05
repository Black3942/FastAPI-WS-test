import asyncio
import websockets
import json
import sys
from datetime import datetime


async def test_websocket_client(server_url: str = "ws://localhost:8000/ws", duration: int = 60):
    print(f"Connecting to {server_url}...")
    
    try:
        async with websockets.connect(server_url) as websocket:
            print(f"Connected successfully at {datetime.now().strftime('%H:%M:%S')}")
            print(f"Listening for notifications... (Press Ctrl+C to disconnect)")
            
            start_time = asyncio.get_event_loop().time()
            
            while True:
                if duration > 0:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= duration:
                        print(f"Duration limit ({duration}s) reached. Disconnecting...")
                        break
                
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    data = json.loads(message)

                    timestamp = datetime.now().strftime('%H:%M:%S')
                    msg_type = data.get('type', 'unknown')
                    
                    print(f"[{timestamp}] {msg_type.upper()}")
                    for key, value in data.items():
                        if key != 'type':
                            print(f"  {key}: {value}")
                    
                except asyncio.TimeoutError:
                    continue
                
    except websockets.exceptions.ConnectionClosed:
        print("Connection closed by server")
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print(f"Disconnected at {datetime.now().strftime('%H:%M:%S')}")


async def test_multiple_clients(num_clients: int = 3, duration: int = 30):
    print(f"Starting {num_clients} concurrent test clients...")
    print(f"Each client will stay connected for {duration} seconds")
    
    tasks = []
    for i in range(num_clients):
        task = asyncio.create_task(
            test_websocket_client(
                server_url=f"ws://localhost:8000/ws",
                duration=duration
            )
        )
        tasks.append(task)
        await asyncio.sleep(0.5)
    
    await asyncio.gather(*tasks)
    print("All test clients finished")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="WebSocket Test Client")
    parser.add_argument(
        "--url",
        default="ws://localhost:8000/ws",
        help="WebSocket server URL (default: ws://localhost:8000/ws)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Connection duration in seconds (0 for infinite, default: 0)"
    )
    parser.add_argument(
        "--multiple",
        type=int,
        default=0,
        help="Number of concurrent clients to spawn (default: 0 = single client)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.multiple > 0:
            asyncio.run(test_multiple_clients(args.multiple, args.duration or 30))
        else:
            asyncio.run(test_websocket_client(args.url, args.duration))
    except KeyboardInterrupt:
        print("Test terminated by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
