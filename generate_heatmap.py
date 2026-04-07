import numpy as np
import matplotlib.pyplot as plt
from scipy import interpolate
import argparse
import os

# Configuration block
CONFIG = {
    'interpolation_method': 'cubic',  
    'grid_resolution': 100,  
    'visualization_params': {
        'color_map': 'jet',  
        'alpha': 0.8  
    }
}

def generate_heatmap(data):
    # FIX 2: Correct CSV column mapping
    # Col 0: Lat, Col 1: Lon, Col 2: Alt, Col 3: Dist, Col 4: RSSI
    y = data[:, 0]  # Latitude (Y-axis)
    x = data[:, 1]  # Longitude (X-axis)
    z = data[:, 4]  # RSSI Signal Strength (Z-axis)

    # Create grid for interpolation
    grid_x, grid_y = np.mgrid[min(x):max(x):CONFIG['grid_resolution']*1j, 
                               min(y):max(y):CONFIG['grid_resolution']*1j]

    # Interpolate using the specified method
    grid_z = interpolate.griddata((x, y), z, (grid_x, grid_y), method=CONFIG['interpolation_method'])

    return grid_x, grid_y, grid_z, x, y

def plot_2d_heatmap(grid_x, grid_y, grid_z, flight_x, flight_y, output_path):
    plt.figure(figsize=(10, 8))
    plt.imshow(grid_z.T, extent=(min(grid_x.flatten()), max(grid_x.flatten()), 
                                 min(grid_y.flatten()), max(grid_y.flatten())), 
               origin='lower', cmap=CONFIG['visualization_params']['color_map'], 
               alpha=CONFIG['visualization_params']['alpha'])
    
    plt.colorbar(label='RSSI Signal Strength (dBm)')
    
    # Plot the drone's actual flight path over the map
    plt.plot(flight_x, flight_y, 'k.', markersize=2, alpha=0.5, label='Drone Flight Path')
    
    plt.title('2D Interpolated RF Heatmap')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.legend()
    plt.savefig(output_path, dpi=300)
    print(f"[+] 2D Heatmap saved to: {output_path}")

def create_3d_surface_plot(grid_x, grid_y, grid_z, output_path):
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    # FIX 3: Passed the full grid_z array
    surf = ax.plot_surface(grid_x, grid_y, grid_z, 
                           cmap=CONFIG['visualization_params']['color_map'], 
                           alpha=CONFIG['visualization_params']['alpha'],
                           linewidth=0, antialiased=True)
    
    fig.colorbar(surf, shrink=0.5, aspect=5, label='RSSI (dBm)')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.set_zlabel('Signal strength (dBm)')
    plt.title('3D Spatial RF Surface Plot')
    
    plt.savefig(output_path, dpi=300)
    print(f"[+] 3D Surface Plot saved to: {output_path}")

def main(input_path, output_path):
    try:
        print(f"[*] Processing {input_path}...")
        
        # FIX 1: Add skiprows=1 to ignore the text headers
        data = np.loadtxt(input_path, delimiter=',', skiprows=1) 
        
        if len(data) == 0:
            print("[!] CSV is empty or invalid.")
            return

        grid_x, grid_y, grid_z, flight_x, flight_y = generate_heatmap(data)

        # FIX 4: Handle the output paths cleanly
        # If the user passed "portfolio_heatmap.png", we use that for 2D, 
        # and auto-generate "portfolio_heatmap_3D.png" for the surface plot.
        path_2d = output_path
        path_3d = output_path.replace('.png', '_3D.png')

        plot_2d_heatmap(grid_x, grid_y, grid_z, flight_x, flight_y, path_2d)
        create_3d_surface_plot(grid_x, grid_y, grid_z, path_3d)

    except Exception as e:
        print(f'[!] Error processing file: {str(e)}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate heatmaps from AP data.')
    parser.add_argument('--input', type=str, required=True, help='Input CSV data file path')
    parser.add_argument('--output', type=str, required=True, help='Output image path (e.g., map.png)')
    args = parser.parse_args()
    main(args.input, args.output)
