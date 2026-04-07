import asyncio
import socket
import math
import time
from mavsdk import System
 
# ─── Configuration ────────────────────────────────────────────────────────────
 
UDP_IP   = "127.0.0.1"
UDP_PORT = 8080
 
# Grid size in GPS degrees.
# ~0.00018° ≈ 20 metres. Increase for larger scan areas.
GRID_OFFSET_DEG = 0.00018
 
# Altitude layers to sweep (metres, relative to launch point).
# Add more values to scan additional floors.
ALTITUDE_LAYERS_M = [5.0, 10.0, 15.0]
 
# Drone must come within this radius (metres) of a waypoint to continue.
WAYPOINT_ACCEPTANCE_RADIUS_M = 1.5
 
# Max time (seconds) to wait for the drone to reach any single waypoint.
# Prevents hanging forever if the drone is stuck.
WAYPOINT_TIMEOUT_S = 45
 
# How long to wait (seconds) after takeoff before starting the grid.
TAKEOFF_SETTLE_S = 8
 
# Telemetry send interval (seconds) — rate-limits UDP packets to C++ engine.
TELEMETRY_INTERVAL_S = 1.0
 
# ─── 3D Distance helper ───────────────────────────────────────────────────────
 
def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle surface distance in metres."""
    R = 6371e3
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi   = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
 
 
def distance_3d(pos, target_lat: float, target_lon: float, target_alt: float) -> float:
    """Euclidean 3D distance from a MAVSDK position object to a target (metres)."""
    d_surface  = haversine_m(pos.latitude_deg, pos.longitude_deg, target_lat, target_lon)
    d_vertical = pos.relative_altitude_m - target_alt
    return math.sqrt(d_surface**2 + d_vertical**2)
 
# ─── Telemetry streaming ──────────────────────────────────────────────────────
 
async def stream_telemetry(drone: System, sock: socket.socket) -> None:
    """
    Background task: forwards GPS telemetry to the C++ spatial engine over UDP.
    Rate-limited by TELEMETRY_INTERVAL_S to avoid flooding the socket.
    """
    print(f"[TELEM] Streaming to {UDP_IP}:{UDP_PORT} every {TELEMETRY_INTERVAL_S}s")
    last_sent = 0.0
 
    async for pos in drone.telemetry.position():
        now = time.monotonic()
        if now - last_sent < TELEMETRY_INTERVAL_S:
            continue
        last_sent = now
 
        lat = pos.latitude_deg
        lon = pos.longitude_deg
        alt = pos.relative_altitude_m
        payload = f"LAT:{lat:.6f}, LON:{lon:.6f}, ALT:{alt:.2f}m"
        sock.sendto(payload.encode(), (UDP_IP, UDP_PORT))
        print(f"[TELEM] Sent → {payload}")
 
# ─── Waypoint navigation ──────────────────────────────────────────────────────
 
async def fly_to(drone: System,
                 lat: float, lon: float,
                 rel_alt: float, abs_alt: float,
                 label: str) -> bool:
    """
    Command the drone to a waypoint and WAIT until it physically arrives.
 
    rel_alt : altitude relative to launch (for distance calculation)
    abs_alt : absolute altitude sent to goto_location (MAVSDK requires this)
 
    Returns True on success, False if the timeout expired.
    """
    print(f"[NAV] Flying to {label} → ({lat:.6f}, {lon:.6f}, {rel_alt:.1f}m rel)")
    await drone.action.goto_location(lat, lon, abs_alt, 0)
 
    deadline = time.monotonic() + WAYPOINT_TIMEOUT_S
    async for pos in drone.telemetry.position():
        dist = distance_3d(pos, lat, lon, rel_alt)
        if dist < WAYPOINT_ACCEPTANCE_RADIUS_M:
            print(f"[NAV] Reached {label} (dist={dist:.2f}m) ✓")
            return True
        if time.monotonic() > deadline:
            print(f"[NAV] ⚠ Timeout reaching {label} — moving on.")
            return False
 
    return False  # stream ended unexpectedly
 
# ─── Grid builder ─────────────────────────────────────────────────────────────
 
def build_grid(origin_lat: float, origin_lon: float) -> list[tuple[float, float, str]]:
    """
    Build a list of (lat, lon, label) waypoints forming a lawnmower pattern
    over the scan area.
 
    The same XY footprint is repeated for every altitude layer defined in
    ALTITUDE_LAYERS_M. Altitude is NOT included here — it is injected in run()
    where we know the absolute altitude reference.
 
    Pattern per layer (viewed from above):
        NW ──→ NE
                ↓
        SW ←── SE
    """
    o  = GRID_OFFSET_DEG
    corners = [
        (origin_lat + o, origin_lon,     "NW"),
        (origin_lat + o, origin_lon + o, "NE"),
        (origin_lat,     origin_lon + o, "SE"),
        (origin_lat,     origin_lon,     "SW"),
    ]
    return corners  # same corners reused per layer in run()
 
# ─── Main ─────────────────────────────────────────────────────────────────────
 
async def run() -> None:
    # --- Socket: created here, closed in finally ---
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
 
    try:
        drone = System()
        print("[INIT] Connecting to drone on UDP port 14540...")
        await drone.connect(system_address="udp://:14540")
 
        print("[INIT] Waiting for connection...")
        async for state in drone.core.connection_state():
            if state.is_connected:
                print("[INIT] Drone connected ✓")
                break
 
        print("[INIT] Waiting for GPS lock...")
        async for health in drone.telemetry.health():
            if health.is_global_position_ok and health.is_home_position_ok:
                print("[INIT] GPS lock acquired ✓")
                break
 
        # Capture origin position and absolute altitude reference
        async for pos in drone.telemetry.position():
            origin_lat = pos.latitude_deg
            origin_lon = pos.longitude_deg
            abs_alt_ref = pos.absolute_altitude_m  # sea-level reference
            break
 
        print(f"[INIT] Origin: ({origin_lat:.6f}, {origin_lon:.6f}), "
              f"abs_alt_ref={abs_alt_ref:.1f}m")
 
        # Start telemetry streaming in background
        asyncio.ensure_future(stream_telemetry(drone, sock))
 
        # Arm and take off
        print("[FLIGHT] Arming motors...")
        await drone.action.arm()
 
        first_layer_alt = ALTITUDE_LAYERS_M[0]
        print(f"[FLIGHT] Taking off to {first_layer_alt}m...")
        await drone.action.set_takeoff_altitude(first_layer_alt)
        await drone.action.takeoff()
        await asyncio.sleep(TAKEOFF_SETTLE_S)
 
        # Build the XY grid pattern
        grid_corners = build_grid(origin_lat, origin_lon)
 
        # ── 3D sweep: same XY corners at every altitude layer ──
        for layer_idx, rel_alt in enumerate(ALTITUDE_LAYERS_M):
            abs_alt = abs_alt_ref + rel_alt
            print(f"\n[GRID] ── Layer {layer_idx + 1}/{len(ALTITUDE_LAYERS_M)}: "
                  f"{rel_alt}m ──")
 
            for (wp_lat, wp_lon, corner) in grid_corners:
                label = f"L{layer_idx + 1}-{corner}"
                await fly_to(drone, wp_lat, wp_lon, rel_alt, abs_alt, label)
 
        # Return to launch
        print("\n[FLIGHT] Grid complete. Returning to launch...")
        await drone.action.return_to_launch()
 
        # Wait for landing (poll altitude instead of a fixed sleep)
        print("[FLIGHT] Waiting for landing...")
        async for pos in drone.telemetry.position():
            if pos.relative_altitude_m < 0.3:
                print("[FLIGHT] Landed ✓")
                break
 
    finally:
        sock.close()
        print("[INIT] UDP socket closed.")
 
 
if __name__ == "__main__":
    asyncio.run(run())
 
