#include <iostream>
#include <string>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cmath>
#include <fstream>
#include <yaml-cpp/yaml.h>

#define BUFFER_SIZE 1024

// Global variables to be loaded from config.yaml
double TARGET_LAT;
double TARGET_LON;
double TARGET_ALT;
int PORT;

double calculate_haversine(double lat1, double lon1, double lat2, double lon2) {
    const double R = 6371e3; 
    double phi1 = lat1 * M_PI / 180;
    double phi2 = lat2 * M_PI / 180;
    double delta_phi = (lat2 - lat1) * M_PI / 180;
    double delta_lambda = (lon2 - lon1) * M_PI / 180;

    double a = sin(delta_phi / 2) * sin(delta_phi / 2) +
               cos(phi1) * cos(phi2) *
               sin(delta_lambda / 2) * sin(delta_lambda / 2);
    double c = 2 * atan2(sqrt(a), sqrt(1 - a));

    return R * c; 
}

int calculate_rssi(double lat, double lon, double alt) {
    double dist_2d = calculate_haversine(lat, lon, TARGET_LAT, TARGET_LON);
    double delta_alt = alt - TARGET_ALT;
    
    double dist_3d = std::sqrt((dist_2d * dist_2d) + (delta_alt * delta_alt));

    if (dist_3d < 1.0) return -30; 
    
    int rssi = -30 - (int)(25 * log10(dist_3d)); 
    if (rssi < -100) return -100;
    return rssi;
}

int main() {
    // 1. LOAD CONFIGURATION DYNAMICALLY
    try {
        YAML::Node config = YAML::LoadFile("config.yaml");
        TARGET_LAT = config["target_ap"]["latitude"].as<double>();
        TARGET_LON = config["target_ap"]["longitude"].as<double>();
        TARGET_ALT = config["target_ap"]["altitude"].as<double>();
        PORT = config["network"]["udp_port"].as<int>();
        std::cout << "[*] Config Loaded. Target AP: " << TARGET_LAT << ", " << TARGET_LON << std::endl;
    } catch (const YAML::Exception& e) {
        std::cerr << "[!] Error parsing config.yaml: " << e.what() << std::endl;
        return 1;
    }

    int sockfd;
    char buffer[BUFFER_SIZE];
    struct sockaddr_in server_addr, client_addr;

    std::ofstream logfile("rogue_ap_hunt.csv");
    // Added AP_Label column for the new Pandas heatmap script!
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

    std::cout << "[*] C++ Engine Secured. Awaiting telemetry..." << std::endl;

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

        double dist_2d = calculate_haversine(current_lat, current_lon, TARGET_LAT, TARGET_LON);
        double delta_alt = current_alt - TARGET_ALT;
        double dist_3d = std::sqrt((dist_2d * dist_2d) + (delta_alt * delta_alt));
        int rssi = calculate_rssi(current_lat, current_lon, current_alt);

        std::cout << "[LOGGED] 3D Dist: " << dist_3d << "m | RSSI: " << rssi << " dBm" << std::endl;
        
        // Log the data with the new AP_Label column so your python heatmap script works perfectly
        logfile << current_lat << "," << current_lon << "," << current_alt << "," << dist_3d << "," << rssi << ",Hidden_Rogue_AP\n";
        logfile.flush(); 
    }

    close(sockfd);
    return 0;
} 
