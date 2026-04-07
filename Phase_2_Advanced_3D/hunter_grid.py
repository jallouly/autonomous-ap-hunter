import asyncio
import socket
import time
import math
import yaml
from mavsdk import System
from mavsdk.action import ActionError

# Load configuration dynamically from the YAML file
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

UDP_IP = config['network']['udp_ip']
UDP_PORT = config['network']['udp_port']
TAKEOFF_ALT = config['flight']['takeoff_alt']
GRID_OFFSET = config['flight']['grid_offset']

def get_distance_3d(lat1, lon1, alt1, lat2, lon2, alt2):
    R = 6371e3
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    dist_2d = R * c
    return math.sqrt(dist_2d**2 + (alt2 - alt1)**2)

async def log_telemetry(drone, sock):
    print(f"[*] Telemetry stream active to {UDP_IP}:{UDP_PORT}")
    last_print = time.time()
    
    async for position in drone.telemetry.position():
        if time.time() - last_print >= 1.0:
            lat = position.latitude_deg
            lon = position.longitude_deg
            alt = position.absolute_altitude_m 
            
            payload = f"LAT:{lat:.6f}, LON:{lon:.6f}, ALT:{alt:.2f}m"
            sock.sendto(payload.encode(), (UDP_IP, UDP_PORT))
            last_print = time.time()

async def goto_and_wait(drone, target_lat, target_lon, target_alt):
    print(f"\n-- Navigating to {target_lat:.5f}, {target_lon:.5f} at {target_alt:.1f}m...")
    
    try:
        await drone.action.goto_location(target_lat, target_lon, target_alt, 0)
    except ActionError as e:
        print(f"   [!] Flight Controller rejected command: {e}")
        return

    start_time = time.time()
    
    async for pos in drone.telemetry.position():
        dist = get_distance_3d(pos.latitude_deg, pos.longitude_deg, pos.absolute_altitude_m,
                               target_lat, target_lon, target_alt)
        
        print(f"\r   -> Distance remaining: {dist:.1f}m    ", end="", flush=True)
        
        if dist < 2.5: 
            print("\n   [+] Waypoint successfully reached!")
            break
            
        if time.time() - start_time > 20:
            print("\n   [!] Waypoint timeout triggered. Proceeding to keep grid moving...")
            break
            
        await asyncio.sleep(0.5)

async def run():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        drone = System()
        print("[*] Connecting to flight controller...")
        await drone.connect(system_address="udpout://127.0.0.1:14540")

        async for state in drone.core.connection_state():
            if state.is_connected:
                break

        print("[*] Waiting for GPS lock...")
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                break

        print("[*] GPS Lock acquired. Letting EKF settle...")
        await asyncio.sleep(3) 

        async for pos in drone.telemetry.position():
            start_lat = pos.latitude_deg
            start_lon = pos.longitude_deg
            ground_abs_alt = pos.absolute_altitude_m
            break

        print(f"[*] Ground absolute altitude established: {ground_abs_alt:.2f}m")

        asyncio.ensure_future(log_telemetry(drone, sock))

        print("\n=== INITIATING 3D SCAN ===\n")
        
        # Now using the dynamic TAKEOFF_ALT from YAML
        await drone.action.set_takeoff_altitude(TAKEOFF_ALT)
        await drone.action.arm()
        await drone.action.takeoff()
        
        print(f"[*] Climbing to initial altitude ({TAKEOFF_ALT}m)...")
        await asyncio.sleep(10) 

        print("[*] Switching to Hold mode to unlock navigation...")
        try:
            await drone.action.hold()
            await asyncio.sleep(2)
        except ActionError as e:
            print(f"[*] Note: Hold mode switch - {e}")

        # Now using the dynamic GRID_OFFSET from YAML
        offset = GRID_OFFSET 
        
        # Scaling the layers based on the dynamic takeoff altitude
        scan_layers = [
            ground_abs_alt + TAKEOFF_ALT, 
            ground_abs_alt + (TAKEOFF_ALT * 2), 
            ground_abs_alt + (TAKEOFF_ALT * 3)
        ]
        
        for current_alt in scan_layers:
            print(f"\n--- Starting scan layer at altitude: {current_alt:.1f}m ---")
            
            waypoints = [
                (start_lat + offset, start_lon, current_alt),               
                (start_lat + offset, start_lon + offset, current_alt),      
                (start_lat, start_lon + offset, current_alt),               
                (start_lat, start_lon, current_alt)                         
            ]
            
            for w_lat, w_lon, w_alt in waypoints:
                await goto_and_wait(drone, w_lat, w_lon, w_alt)

        print("\n=== SCAN COMPLETE. RETURNING TO LAUNCH ===")
        await drone.action.return_to_launch()
        await asyncio.sleep(15)

    finally:
        print("\n[*] Closing network socket safely.")
        sock.close()

if __name__ == "__main__":
    asyncio.run(run())
