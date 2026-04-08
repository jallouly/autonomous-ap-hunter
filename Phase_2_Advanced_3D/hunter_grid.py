import asyncio
import socket
import time
import math
import yaml
from mavsdk import System
from mavsdk.action import ActionError

# ─── Config ───────────────────────────────────────────────────────────────────

try:
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("[!] Error: config.yaml not found.")
    exit(1)

UDP_IP      = config['network']['udp_ip']
UDP_PORT    = config['network']['udp_port']
TAKEOFF_ALT = config['flight']['takeoff_alt']
GRID_OFFSET = config['flight']['grid_offset']

# ─── Shared position state ────────────────────────────────────────────────────
#
# FIX: Instead of two coroutines each opening their own
# drone.telemetry.position() loop (which starves each other), we have ONE
# background task that owns the stream and writes the latest position here.
# All other functions read from this dict — zero stream contention.

_pos = {
    "lat": None,
    "lon": None,
    "alt": None,   # absolute altitude (m)
    "ready": False
}

# ─── Math ─────────────────────────────────────────────────────────────────────

def distance_3d(lat1, lon1, alt1, lat2, lon2, alt2):
    R = 6371e3
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi    = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    dist_2d = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return math.sqrt(dist_2d**2 + (alt2 - alt1)**2)

# ─── Single telemetry owner ───────────────────────────────────────────────────

async def position_updater(drone):
    """
    THE ONLY coroutine that reads drone.telemetry.position().
    Writes every incoming packet into _pos immediately — no sleep inside the loop.
    Rate-limiting for UDP is handled separately in telemetry_sender().
    """
    async for pos in drone.telemetry.position():
        _pos["lat"]   = pos.latitude_deg
        _pos["lon"]   = pos.longitude_deg
        _pos["alt"]   = pos.absolute_altitude_m
        _pos["ready"] = True
        # No sleep here — drain the queue at full speed


async def telemetry_sender(sock):
    """
    Reads from _pos (not from the drone stream) and forwards to C++ engine at 1 Hz.
    Completely decoupled from the MAVSDK queue — no contention.
    """
    print(f"[TELEM] Sender active to {UDP_IP}:{UDP_PORT} at 1 Hz")
    while True:
        if _pos["ready"]:
            payload = f"LAT:{_pos['lat']:.6f}, LON:{_pos['lon']:.6f}, ALT:{_pos['alt']:.2f}m"
            sock.sendto(payload.encode(), (UDP_IP, UDP_PORT))
        await asyncio.sleep(1.0)  # 1 Hz rate limit — safe here, outside the stream loop

# ─── Waypoint navigation ──────────────────────────────────────────────────────

async def goto_and_wait(drone, target_lat, target_lon, target_alt, timeout=45):
    """
    Commands the drone to a waypoint and polls _pos until arrival.
    Does NOT open its own telemetry stream — reads the shared _pos dict instead.
    """
    print(f"\n-- Navigating to ({target_lat:.5f}, {target_lon:.5f}, {target_alt:.1f}m abs)")

    try:
        await drone.action.goto_location(target_lat, target_lon, target_alt, 0)
    except ActionError as e:
        print(f"   [!] Command rejected: {e}")
        return

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if _pos["ready"]:
            dist = distance_3d(
                _pos["lat"], _pos["lon"], _pos["alt"],
                target_lat,  target_lon,  target_alt
            )
            print(f"\r   -> Distance remaining: {dist:.1f}m    ", end="", flush=True)

            if dist < 2.5:
                print("\n   [+] Waypoint reached!")
                return

        await asyncio.sleep(0.5)  # poll every 500ms — fine here, not inside async-for

    print("\n   [!] Timeout — moving to next waypoint.")

# ─── Main ─────────────────────────────────────────────────────────────────────

async def run():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        drone = System()
        print("[*] Connecting to flight controller...")
        await drone.connect(system_address="udp://:14540")

        async for state in drone.core.connection_state():
            if state.is_connected:
                print("[*] Connected!")
                break

        print("[*] Waiting for GPS lock...")
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("[*] GPS lock acquired.")
                break

        print("[*] Letting EKF settle (3s)...")
        await asyncio.sleep(3)

        # Prime _pos by reading one packet before handing off to the background task
        async for pos in drone.telemetry.position():
            _pos["lat"]    = pos.latitude_deg
            _pos["lon"]    = pos.longitude_deg
            _pos["alt"]    = pos.absolute_altitude_m
            _pos["ready"]  = True
            start_lat      = pos.latitude_deg
            start_lon      = pos.longitude_deg
            ground_abs_alt = pos.absolute_altitude_m
            break

        print(f"[*] Home: ({start_lat:.6f}, {start_lon:.6f}), abs_alt={ground_abs_alt:.2f}m")

        # Launch the ONE stream owner and the rate-limited UDP sender
        asyncio.ensure_future(position_updater(drone))
        asyncio.ensure_future(telemetry_sender(sock))

        print("\n=== INITIATING 3D SCAN ===\n")

        await drone.action.set_takeoff_altitude(TAKEOFF_ALT)
        await drone.action.arm()
        await drone.action.takeoff()

        print(f"[*] Climbing to {TAKEOFF_ALT}m...")
        await asyncio.sleep(12)

        print("[*] Transitioning to Hold mode...")
        try:
            await drone.action.hold()
            await asyncio.sleep(2)
        except ActionError as e:
            print(f"[*] Mode switch note: {e}")

        scan_layers = [
            ground_abs_alt + TAKEOFF_ALT,
            ground_abs_alt + (TAKEOFF_ALT * 2),
            ground_abs_alt + (TAKEOFF_ALT * 3),
        ]

        offset = GRID_OFFSET

        for layer_idx, current_alt in enumerate(scan_layers):
            print(f"\n--- Layer {layer_idx + 1}/{len(scan_layers)}: {current_alt:.1f}m abs ---")

            waypoints = [
                (start_lat + offset, start_lon,          current_alt),
                (start_lat + offset, start_lon + offset, current_alt),
                (start_lat,          start_lon + offset, current_alt),
                (start_lat,          start_lon,          current_alt),
            ]

            for wp_lat, wp_lon, wp_alt in waypoints:
                await goto_and_wait(drone, wp_lat, wp_lon, wp_alt)

        print("\n=== SCAN COMPLETE — RETURNING TO LAUNCH ===")
        await drone.action.return_to_launch()

        print("[*] Waiting for landing...")
        while True:
            if _pos["ready"] and _pos["alt"] < ground_abs_alt + 0.5:
                print("[*] Landed.")
                break
            await asyncio.sleep(1)

    finally:
        sock.close()
        print("[*] Socket closed.")


if __name__ == "__main__":
    asyncio.run(run())
