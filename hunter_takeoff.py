import asyncio
import socket
from mavsdk import System

# Configure the UDP socket to talk to C++
UDP_IP = "127.0.0.1"
UDP_PORT = 8080
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

async def log_telemetry(drone):
    """Background task to stream GPS data to the C++ server."""
    print(f"Starting telemetry stream to {UDP_IP}:{UDP_PORT}...")
    
    async for position in drone.telemetry.position():
        lat = position.latitude_deg
        lon = position.longitude_deg
        alt = position.relative_altitude_m
        
        # Format the data as a simple string payload
        payload = f"LAT:{lat:.6f}, LON:{lon:.6f}, ALT:{alt:.2f}m"
        
        # Fire the packet over the network to the C++ listener
        sock.sendto(payload.encode(), (UDP_IP, UDP_PORT))
        print(f"[PYTHON SENT] {payload}")
        
        await asyncio.sleep(1)

async def run():
    drone = System()
    print("Connecting to drone on UDP port 14540...")
    await drone.connect(system_address="udp://:14540")

    print("Waiting for drone to connect...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            break

    print("Waiting for GPS lock...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break

    # Start the telemetry logging in the background
    asyncio.ensure_future(log_telemetry(drone))

    print("-- Arming Motors")
    await drone.action.arm()

    print("-- Taking off")
    await drone.action.takeoff()

    # Let it fly and stream data for 15 seconds
    await asyncio.sleep(15)

    print("-- Landing")
    await drone.action.land()
    await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run())
