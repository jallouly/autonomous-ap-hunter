
# Autonomous 3D Spatial Network Mapper (SITL Simulation)

##  Project Overview
Traditional rogue access point (AP) detection relies on 2D floor plans and manual walking grids, which are slow and highly inaccurate for multi-story enterprise environments. 
This project bridges **Cybersecurity** and **Aerodynamics** by engineering a simulated drone platform that autonomously executes a 3D flight grid, logging GPS telemetry and calculating spatial distances to detect and map hidden network vulnerabilities.

##  Key Features
* **Autonomous Flight Grid:** Python flight logic utilizing MAVSDK to command a PX4-powered quadcopter in a Gazebo 3D physics engine.
* **C++ Spatial Engine:** A low-level UDP socket server that acts as the network analysis engine. It catches live flight telemetry and calculates simulated Wi-Fi RSSI attenuation based on geospatial Haversine distances.
* **Inter-Process Communication (IPC):** Real-time, asynchronous telemetry streaming bridging Python flight controls with C++ security payloads via local UDP sockets.
* **Vulnerability Visualization:** Automated data logging to CSV, parsed by Pandas and Matplotlib to generate a color-coded geographic heatmap of the target area.

##  Technology Stack
* **Languages:** C++, Python 3
* **Libraries:** MAVSDK, Asyncio, Pandas, Matplotlib, C++ `<sys/socket.h>`
* **Simulation & OS:** Ubuntu Linux, PX4 Autopilot, Gazebo SITL


## ⚙️ How to Run the Simulation

**1. Launch the Physics Engine (Terminal 1)**
```bash
cd PX4-Autopilot
make px4_sitl gz_x500
```

**2. Start the C++ Spatial Sniffer (Terminal 2)**
```bash
g++ mock_sniffer.cpp -o mock_sniffer
./mock_sniffer
```

**3. Execute the Autonomous Flight Plan (Terminal 3)**
```bash
source drone_env/bin/activate
python3 hunter_grid.py
```

**4. Generate the Heatmap (After flight completes)**
```bash
python3 generate_heatmap.py
```

##  Future Roadmap (Hardware Phase)
This repository represents **Phase 1 (Software-In-The-Loop)**. 
Phase 2 will involve porting this exact C++ and Python codebase onto a physical Raspberry Pi Zero W, attaching a high-gain monitor-mode Wi-Fi antenna, and mounting the payload to a custom-built quadcopter for real-world RF analysis.

---
*Developed by Mohamed Aziz Jallouli*
```
