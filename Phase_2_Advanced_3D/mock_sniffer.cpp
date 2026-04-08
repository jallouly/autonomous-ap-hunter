#include <iostream>
#include <string>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cmath>
#include <fstream>
#include <unordered_map>
#include <random>
#include <iomanip>
#include <sstream>
#include <yaml-cpp/yaml.h>

#define BUFFER_SIZE 1024

// Structure to hold our dynamically spawned APs
struct RogueAP {
    std::string mac_address;
    double lat;
    double lon;
    double alt;
};

// Global Hash Map to store our unknown APs
std::unordered_map<std::string, RogueAP> active_aps;
int PORT;

// Random MAC Address Generator
std::string generate_mac() {
    std::random_device rd;
    std::mt19937 gen(rd()); // FIXED: Corrected to mt19937
    std::uniform_int_distribution<> dis(0, 255);
    std::stringstream ss;
    for (int i = 0; i < 6; ++i) {
        ss << std::setfill('0') << std::setw(2) << std::hex << dis(gen);
        if (i < 5) ss << ":";
    }
    return ss.str();
}

double calculate_haversine(double lat1, double lon1, double lat2, double lon2) {
    const double R = 6371e3; 
    double phi1 = lat1 * M_PI / 180;
    double phi2 = lat2 * M_PI / 180;
    double delta_phi = (lat2 - lat1) * M_PI / 180;
    double delta_lambda = (lon2 - lon1) * M_PI / 180;
    double a = sin(delta_phi / 2) * sin(delta_phi / 2) +
               cos(phi1) * cos(phi2) *
               sin(delta_lambda / 2) * sin(delta_lambda / 2);
    return R * 2 * atan2(sqrt(a), sqrt(1 - a));
}

int calculate_rssi(double dist_3d) {
    if (dist_3d < 1.0) return -30; 
    int rssi = -30 - (int)(25 * log10(dist_3d)); 
    if (rssi < -100) return -100;
    return rssi;
}

int main() {
    double center_lat, center_lon, center_alt;
    
    // 1. Load the "Zone" from config
    try {
        YAML::Node config = YAML::LoadFile("config.yaml");
        center_lat = config["target_ap"]["latitude"].as<double>();
        center_lon = config["target_ap"]["longitude"].as<double>();
        center_alt = config["target_ap"]["altitude"].as<double>();
        PORT = config["network"]["udp_port"].as<int>();
    } catch (const YAML::Exception& e) {
        std::cerr << "[!] Error parsing config.yaml: " << e.what() << std::endl;
        return 1;
    }

    // 2. The Spawner: Scatter random APs in the scan zone
    std::cout << "\n[*] INITIATING PHASE 3 DYNAMIC DISCOVERY..." << std::endl;
    std::random_device rd;
    std::mt19937 gen(rd()); // FIXED: Corrected to mt19937
    // Scatter APs roughly within a 50m radius of the config coordinates
    std::uniform_real_distribution<> offset_dist(-0.0004, 0.0004); 
    std::uniform_real_distribution<> alt_dist(0.0, 20.0); 
    std::uniform_int_distribution<> ap_count_dist(3, 5); 

    int num_aps = ap_count_dist(gen);
    std::cout << "[*] Spawning " << num_aps << " hidden Rogue APs..." << std::endl;
    
    for (int i = 0; i < num_aps; ++i) {
        RogueAP ap;
        ap.mac_address = generate_mac();
        ap.lat = center_lat + offset_dist(gen);
        ap.lon = center_lon + offset_dist(gen);
        ap.alt = center_alt + alt_dist(gen);
        active_aps[ap.mac_address] = ap;
        std::cout << "  -> [GHOST AP GENERATED] MAC: " << ap.mac_address 
                  << " | Alt: " << std::fixed << std::setprecision(1) << ap.alt << "m" << std::endl;
    }

    // 3. Setup Network
    int sockfd;
    char buffer[BUFFER_SIZE];
    struct sockaddr_in server_addr, client_addr;

    std::ofstream logfile("rogue_ap_hunt.csv");
    logfile << "Latitude,Longitude,Altitude,Distance_3D_m,RSSI_dBm,AP_Label\n";

    if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
        std::cerr << "[ERROR] Socket creation failed" << std::endl;
        return 1;
    }

    memset(&server_addr, 0, sizeof(server_addr));
    memset(&client_addr, 0, sizeof(client_addr));

    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);

    if (bind(sockfd, (const struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "[ERROR] Bind failed" << std::endl;
        return 1;
    }

    std::cout << "\n[*] Engine Secured. Listening for drone telemetry on UDP " << PORT << "..." << std::endl;

    // 4. The Tracker Loop
    socklen_t len;
    while (true) {
        len = sizeof(client_addr);
        int n = recvfrom(sockfd, (char *)buffer, BUFFER_SIZE, MSG_WAITALL, (struct sockaddr *)&client_addr, &len);
        
        if (n < 0) continue;
        if (n >= BUFFER_SIZE) n = BUFFER_SIZE - 1; 
        buffer[n] = '\0'; 

        float current_lat = 0.0, current_lon = 0.0, current_alt = 0.0;
        if (sscanf(buffer, "LAT:%f, LON:%f, ALT:%fm", &current_lat, &current_lon, &current_alt) != 3) {
            continue; 
        }

        // Check distance to ALL active APs simultaneously
        for (const auto& pair : active_aps) {
            const RogueAP& ap = pair.second;
            
            double dist_2d = calculate_haversine(current_lat, current_lon, ap.lat, ap.lon);
            double delta_alt = current_alt - ap.alt;
            double dist_3d = std::sqrt((dist_2d * dist_2d) + (delta_alt * delta_alt));
            int rssi = calculate_rssi(dist_3d);

            // SIGNAL CUTOFF: If it's weaker than -85 dBm, the drone "can't hear it"
            if (rssi > -85) {
                std::cout << "[DETECTED] MAC: " << ap.mac_address << " | Dist: " 
                          << std::fixed << std::setprecision(1) << dist_3d << "m | RSSI: " << rssi << " dBm" << std::endl;
                
                logfile << current_lat << "," << current_lon << "," << current_alt << "," 
                        << dist_3d << "," << rssi << "," << ap.mac_address << "\n";
                logfile.flush(); 
            }
        }
    }

    close(sockfd);
    return 0;
}