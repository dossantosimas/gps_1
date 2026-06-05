import asyncio

# Define the IP and Port your server will listen on
# Use "0.0.0.0" to accept connections from any network interface
SERVER_HOST = "0.0.0.0"  
SERVER_PORT = 8000  # Ensure this port is open in your router/firewall

async def handle_tracker_client(reader, writer):
    """
    Handles the lifecycle of a single GNXIS tracker connection.
    """
    client_address = writer.get_extra_info('peername')
    print(f"[*] New connection established from {client_address}")

    try:
        while True:
            # Trackers send data in small chunks; 1024 bytes is plenty
            data = await reader.read(1024)
            
            if not data:
                print(f"[-] Tracker {client_address} disconnected cleanly.")
                break

            # Try to decode as text, fallback to Hexadecimal string if binary
            try:
                decoded_data = data.decode('utf-8').strip()
                print(f"[{client_address}] Raw Text Data: {decoded_data}")
            except UnicodeDecodeError:
                hex_data = data.hex().upper()
                print(f"[{client_address}] Raw Hex Data: {hex_data}")

            # PROTOCOL HANDSHAKE (Crucial for most trackers)
            # If the tracker sends a login packet, it expects a small response back.
            # Example for standard GT06/Concox trackers (common base for GNXIS):
            # If the data starts with '7878' (Hex), you must send a confirmation byte back.
            if data.startswith(b'\x78\x78') and len(data) > 4:
                # Basic handshake response pattern (adjust based on your exact sub-model)
                # Usually Echoes back Start bytes + Protocol ID + Serial Number + Error Check
                response = b'\x78\x78\x05\x01' + data[4:6] + b'\x00\x05\x99\x99\x0D\x0A'
                writer.write(response)
                await writer.drain()
                print(f"[->] Handshake response sent to {client_address}")

    except asyncio.CancelledError:
        print(f"[-] Connection with {client_address} was cancelled.")
    except Exception as e:
        print(f"[!] Error handling tracker {client_address}: {e}")
    finally:
        writer.close()
        await writer.wait_closed()
        print(f"[*] Connection closed for {client_address}")

async def main():
    # Start the TCP socket server
    server = await asyncio.start_server(handle_tracker_client, SERVER_HOST, SERVER_PORT)
    print(f"[*] GNXIS Server running on {SERVER_HOST}:{SERVER_PORT}")
    print("[*] Waiting for GPS trackers to connect...")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Server stopped by user.")
