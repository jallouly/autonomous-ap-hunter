import asyncio
import socket
import time
from mavsdk import System

UDP_IP = "127.0.0.1"
UDP_PORT = 8080
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

async def log_telemetry(drone):
    """Background task to stream GPS data without blocking the queue."""
    print(f"Starting telemetry stream to {UDP_IP}:{UDP_PORT}...")
    last_print = time.time()
    
    # The async loop now runs at full speed, draining the queue instantly
    async for position in drone.telemetry.position():
        # We only send a packet if 1 second has passed
        if time.time() - last_print >= 1.0:
            lat = position.latitude_deg
            lon = position.longitude_deg
            alt = position.relative_altitude_m
            
            payload = f"LAT:{lat:.6f}, LON:{lon:.6f}, ALT:{alt:.2f}m"
            sock.sendto(payload.encode(), (UDP_IP, UDP_PORT))
            print(f"[PYTHON SENT] {payload}")
            last_print = time.time()

async def run():
    drone = System()
    print("Connecting to drone on UDP port 14540...")
    await drone.connect(system_address="udp://:14540")

    async for state in drone.core.connection_state():
        if state.is_connected:
            break

    print("Waiting for GPS lock...")
    async for health in drone.telemetry.health():
        if health.is_global_position_ok and health.is_home_position_ok:
            break

    # Get the starting absolute altitude (needed for grid navigation)
    async for pos in drone.telemetry.position():
        initial_lat = pos.latitude_deg
        initial_lon = pos.longitude_deg
        abs_alt = pos.absolute_altitude_m
        break

    asyncio.ensure_future(log_telemetry(drone))

    print("-- Arming Motors")
    await drone.action.arm()

    print("-- Taking off to 5 meters")
    await drone.action.set_takeoff_altitude(5.0)
    await drone.action.takeoff()
    await asyncio.sleep(8) # Wait 8 seconds to reach altitude

    # Roughly 20 meters in GPS coordinates
    offset = 0.00018 

    # Define a 4-point square grid search pattern
    waypoints = [
        (initial_lat + offset, initial_lon),               # Point 1: North
        (initial_lat + offset, initial_lon + offset),      # Point 2: North-East
        (initial_lat, initial_lon + offset),               # Point 3: East
        (initial_lat, initial_lon)                         # Point 4: Back to start
    ]

    flight_alt = abs_alt + 5.0 # Keep it 5 meters above sea level

    for i, (w_lat, w_lon) in enumerate(waypoints):
        print(f"-- Flying to Waypoint {i+1}...")
        # goto_location(latitude, longitude, absolute_altitude, yaw_angle)
        await drone.action.goto_location(w_lat, w_lon, flight_alt, 0)
        await asyncio.sleep(10) # Give the drone 10 seconds to fly to each point

    print("-- Returning to Launch and Landing")
    await drone.action.return_to_launch()
    await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(run())
