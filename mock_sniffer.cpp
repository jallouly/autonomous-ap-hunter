#include <iostream>
#include <string>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <cmath>
#include <fstream> // Added for file writing

#define PORT 8080
#define BUFFER_SIZE 1024

const double TARGET_LAT = 47.398000;
const double TARGET_LON = 8.546200;

double calculate_distance(double lat1, double lon1, double lat2, double lon2) {
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

int calculate_rssi(double distance_meters) {
    if (distance_meters < 1.0) return -30; 
    int rssi = -30 - (int)(20 * log10(distance_meters));
    if (rssi < -100) return -100;
    return rssi;
}

int main() {
    int sockfd;
    char buffer[BUFFER_SIZE];
    struct sockaddr_in server_addr, client_addr;

    // Open a CSV file and write the header row
    std::ofstream logfile("rogue_ap_hunt.csv");
    logfile << "Latitude,Longitude,Altitude,Distance_m,RSSI_dBm\n";

    if ((sockfd = socket(AF_INET, SOCK_DGRAM, 0)) < 0) {
        std::cerr << "Socket creation failed" << std::endl;
        return 1;
    }

    memset(&server_addr, 0, sizeof(server_addr));
    memset(&client_addr, 0, sizeof(client_addr));

    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(PORT);

    if (bind(sockfd, (const struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        std::cerr << "Bind failed" << std::endl;
        return 1;
    }

    std::cout << "[*] C++ Spatial Engine Active. Saving data to rogue_ap_hunt.csv..." << std::endl;

    socklen_t len;
    while (true) {
        len = sizeof(client_addr);
        int n = recvfrom(sockfd, (char *)buffer, BUFFER_SIZE, MSG_WAITALL, (struct sockaddr *)&client_addr, &len);
        buffer[n] = '\0'; 

        float current_lat = 0.0, current_lon = 0.0, current_alt = 0.0;
        
        if (sscanf(buffer, "LAT:%f, LON:%f, ALT:%fm", &current_lat, &current_lon, &current_alt) == 3) {
            double distance = calculate_distance(current_lat, current_lon, TARGET_LAT, TARGET_LON);
            int rssi = calculate_rssi(distance);

            std::cout << "[LOGGED] Dist: " << distance << "m | RSSI: " << rssi << " dBm" << std::endl;
            
            // Save the exact variables to the CSV file
            logfile << current_lat << "," << current_lon << "," << current_alt << "," << distance << "," << rssi << "\n";
            logfile.flush(); // Ensure data writes immediately
        }
    }

    close(sockfd);
    return 0;
}
