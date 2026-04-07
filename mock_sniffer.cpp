
#include <iostream>
#include <string>
#include <cstring>
#include <cmath>
#include <vector>
#include <fstream>
#include <csignal>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
 
// ─── Configuration ────────────────────────────────────────────────────────────
 
#define PORT        8080
#define BUFFER_SIZE 1024
 
// Log-Distance Path Loss exponent (n):
//   2.0 = free space / open outdoor
//   2.7 = open office / indoor line-of-sight
//   3.5 = typical office with walls
//   4.5 = dense concrete / multi-floor
const double PATH_LOSS_EXPONENT = 3.5;
 
// Transmit power assumed at 1 metre reference distance (dBm).
// Typical Wi-Fi AP: +20 dBm TX, ~-30 dBm measured at 1m.
const double RSSI_AT_1M = -30.0;
 
// ─── Known / Simulated AP Targets ─────────────────────────────────────────────
//
// In a real deployment these would be loaded from a config file.
// For SITL simulation these are placed near the Gazebo default spawn point
// (Zurich, ~47.398°N 8.546°E) so the drone's test grid flies over them.
 
struct AccessPoint {
    std::string label;
    double lat;
    double lon;
    double alt_m; // floor-level altitude above sea level
};
 
const std::vector<AccessPoint> KNOWN_APS = {
    { "AP-CORPORATE-01", 47.398000, 8.546200, 0.0 },
    { "AP-ROGUE-SHADOW",  47.398100, 8.546400, 0.0 },
    { "AP-GUEST-NET",     47.397900, 8.545900, 3.0 }, // second floor
};
 
// ─── Globals for signal handler ───────────────────────────────────────────────
 
static int      g_sockfd  = -1;
static bool     g_running = true;
std::ofstream   g_logfile;
 
void handle_sigint(int) {
    std::cout << "\n[*] Shutting down cleanly..." << std::endl;
    g_running = false;
    if (g_sockfd >= 0) close(g_sockfd);
    if (g_logfile.is_open()) g_logfile.close();
}
 
// ─── Math helpers ─────────────────────────────────────────────────────────────
 
// Haversine great-circle distance (metres) — 2D surface only.
double haversine(double lat1, double lon1, double lat2, double lon2) {
    const double R = 6371e3;
    double phi1   = lat1 * M_PI / 180.0;
    double phi2   = lat2 * M_PI / 180.0;
    double dphi   = (lat2 - lat1) * M_PI / 180.0;
    double dlambda = (lon2 - lon1) * M_PI / 180.0;
 
    double a = std::sin(dphi / 2) * std::sin(dphi / 2)
             + std::cos(phi1)   * std::cos(phi2)
             * std::sin(dlambda / 2) * std::sin(dlambda / 2);
 
    return R * 2.0 * std::atan2(std::sqrt(a), std::sqrt(1.0 - a));
}
 
// Full 3D Euclidean distance: combines surface distance + altitude delta.
double distance_3d(double lat1, double lon1, double alt1,
                   double lat2, double lon2, double alt2) {
    double d_surface = haversine(lat1, lon1, lat2, lon2);
    double d_vertical = alt1 - alt2;
    return std::sqrt(d_surface * d_surface + d_vertical * d_vertical);
}
// Log-Distance Path Loss model — physically accurate for indoor/outdoor Wi-Fi.
// Returns RSSI in dBm. Clamped to [-100, -20] (receiver sensitivity floor).
double calculate_rssi(double distance_m) {
    if (distance_m < 1.0) return RSSI_AT_1M; // reference distance guard
    double rssi = RSSI_AT_1M - 10.0 * PATH_LOSS_EXPONENT * std::log10(distance_m);
    if (rssi > -20.0)  return -20.0;
    if (rssi < -100.0) return -100.0;
    return rssi;
}
// ─── Main ─────────────────────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    // --- Output file path (argv[1] or default) ---
    std::string csv_path = (argc > 1) ? argv[1] : "rogue_ap_hunt.csv";
    g_logfile.open(csv_path);
    if (!g_logfile.is_open()) {
        std::cerr << "[!] Cannot open output file: " << csv_path << std::endl;
        return 1;
    }
    // CSV header — one row per (telemetry packet × AP)
    g_logfile << "Latitude,Longitude,Altitude_m,AP_Label,"
              << "Distance_3D_m,RSSI_dBm\n";
    // --- UDP socket setup ---
    struct sockaddr_in server_addr, client_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    memset(&client_addr, 0, sizeof(client_addr));
    g_sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (g_sockfd < 0) {
        std::cerr << "[!] Socket creation failed" << std::endl;
        return 1;
    } 
    server_addr.sin_family      = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port        = htons(PORT);
    if (bind(g_sockfd, (const struct sockaddr*)&server_addr,
             sizeof(server_addr)) < 0) {
        std::cerr << "[!] Bind failed on port " << PORT << std::endl;
        close(g_sockfd);
        return 1;
    } 
    // --- Register clean shutdown on Ctrl-C ---
    std::signal(SIGINT, handle_sigint);

    std::cout << "[*] C++ Spatial Engine active on UDP port " << PORT << std::endl;
    std::cout << "[*] Tracking " << KNOWN_APS.size() << " access points." << std::endl;
    std::cout << "[*] Logging to: " << csv_path << std::endl;
    std::cout << "[*] Press Ctrl-C to stop.\n" << std::endl;
    // --- Receive loop ---
    char buffer[BUFFER_SIZE];
    socklen_t client_len = sizeof(client_addr); 
    while (g_running) {
        int n = recvfrom(g_sockfd, buffer, BUFFER_SIZE - 1, 0,
                         (struct sockaddr*)&client_addr, &client_len);

        if (n <= 0 || n >= BUFFER_SIZE) {
            if (n < 0 && g_running)
                std::cerr << "[!] recvfrom error, skipping packet." << std::endl;
            continue;
        }
        buffer[n] = '\0';
        double current_lat = 0.0, current_lon = 0.0, current_alt = 0.0;
       int parsed = sscanf(buffer,
                            "LAT:%lf, LON:%lf, ALT:%lfm",
                            &current_lat, &current_lon, &current_alt);
        if (parsed != 3) {
            std::cerr << "[!] Malformed packet, discarding: " << buffer << std::endl;
            continue;
        }
        for (const auto& ap : KNOWN_APS) {
            double dist = distance_3d(current_lat, current_lon, current_alt,
                                      ap.lat,        ap.lon,      ap.alt_m);
            double rssi = calculate_rssi(dist);
            std::cout << "[" << ap.label << "] "
                      << "Dist: " << std::fixed
                      << dist << " m | RSSI: " << rssi << " dBm" << std::endl;
            g_logfile << current_lat << ","
                      << current_lon << ","
                      << current_alt << ","
                      << ap.label    << ","
                      << dist        << ","
                      << rssi        << "\n";
        }
        g_logfile.flush();
    }
    // Cleanup (also called by signal handler)
    if (g_sockfd >= 0) close(g_sockfd);
    if (g_logfile.is_open()) g_logfile.close();
    std::cout << "[*] Data saved to " << csv_path << std::endl;
    return 0;
}
 
