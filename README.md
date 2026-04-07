# Autonomous 3D Spatial Network Mapper (SITL Simulation)

## Project Overview
Traditional rogue access point (AP) detection relies on 2D floor plans and manual walking grids. This project is a physics-based, 3D autonomous drone simulation designed to hunt and map unknown RF signals in three-dimensional space. 

By combining MAVSDK drone telemetry, a custom C++ memory-safe UDP network engine, and Scipy spatial interpolation, this system creates highly accurate 3D topographical signal heatmaps to pinpoint rogue APs.

## Project Evolution

### 📁 Phase 1: Basic Simulation
The initial proof-of-concept. It established the MAVSDK connection, flew a flat 2D search grid, and generated basic scatter plots. *Kept for historical progression.*

### 📁 Phase 2: Advanced 3D & Data Science (Current)
A massive architectural overhaul representing the current state of the project.
* **True 3D Navigation:** Python flight scripts dynamically sweep across multiple altitudes (e.g., 5m, 10m, 15m) with real-time waypoint state verification and timeout tolerances.
* **Central Configuration:** A `config.yaml` file drives both the Python flight controller and the C++ physics engine, allowing dynamic reconfiguration of network ports and scan areas without recompiling.
* **Mathematical Verification:** Navigation logic and 3D spatial Haversine calculations are verified via a `pytest` suite.
* **Memory-Safe C++ Engine:** The UDP sniffer is hardened against buffer overflows and malformed packet injections.
* **Perceptual Data Science:** Replaced basic scatter plots with `scipy.interpolate` to generate true continuous 2D heatmaps and 3D topological surfaces using the `viridis` colormap. Support for multi-AP tracking via Pandas.

## Usage (Phase 2)

### 1. Launch the Stack
Start the Gazebo/PX4 simulator, then run the network engine and flight controller from the Phase 2 folder:
```bash
# Terminal 1: Launch C++ Engine
./mock_sniffer

# Terminal 2: Launch Autonomous Flight
python3 hunter_grid.py
2. Generate the Heatmaps
Once the drone lands, run the data science pipeline on the generated CSV telemetry:

Bash
python3 generate_heatmap.py --input rogue_ap_hunt.csv --output scan_results
This will output scan_results_[AP_Name]_2D.png and scan_results_[AP_Name]_3D.png.

Future Work: Phase 3 & Beyond (Perfecting the Theory)
Before moving to physical hardware, the immediate next steps focus on perfecting the theoretical models and simulation algorithms. Future versions of this codebase will introduce:

Dynamic Discovery: Upgrading the C++ spatial engine to identify and track completely unknown signal anomalies, rather than relying on a pre-configured config.yaml target.

Algorithmic Pathfinding: Replacing the rigid, pre-planned 3D grid with a gradient-ascent flight algorithm. The drone will process the C++ RSSI telemetry in real-time and dynamically alter its flight path to autonomously "climb" the signal strength gradient.

Complex Environmental Modeling: Introducing simulated RF obstacles (walls, interference) to test the robustness of the interpolation engine.

Phase 4: The Hardware Port
Only once the algorithmic foundation is flawless in SITL will the system be deployed to the real world. This will involve porting the logic to a Raspberry Pi Zero W mounted on a physical drone, replacing the mock_sniffer with a root-privileged libpcap engine to capture raw 802.11 beacon frames in monitor mode.
