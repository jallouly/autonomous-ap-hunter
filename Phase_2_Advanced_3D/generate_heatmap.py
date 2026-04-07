import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import interpolate
import argparse
import os

# Configuration block
CONFIG = {
    'interpolation_method': 'cubic',  
    'grid_resolution': 150,  # Bumped up for smoother curves
    'visualization_params': {
        'color_map': 'viridis',  # Upgraded from 'jet' to perceptual standard
        'alpha': 0.85  
    }
}

def generate_heatmap(x, y, z):
    # Create dense grid for interpolation
    grid_x, grid_y = np.mgrid[min(x):max(x):CONFIG['grid_resolution']*1j, 
                               min(y):max(y):CONFIG['grid_resolution']*1j]

    # Interpolate signal bleed between actual flight paths
    grid_z = interpolate.griddata((x, y), z, (grid_x, grid_y), method=CONFIG['interpolation_method'])
    return grid_x, grid_y, grid_z

def plot_2d_heatmap(grid_x, grid_y, grid_z, flight_x, flight_y, ap_name, output_path):
    plt.figure(figsize=(10, 8))
    plt.imshow(grid_z.T, extent=(min(grid_x.flatten()), max(grid_x.flatten()), 
                                 min(grid_y.flatten()), max(grid_y.flatten())), 
               origin='lower', cmap=CONFIG['visualization_params']['color_map'], 
               alpha=CONFIG['visualization_params']['alpha'])
    
    plt.colorbar(label='RSSI Signal Strength (dBm)')
    plt.plot(flight_x, flight_y, 'w.', markersize=1.5, alpha=0.4, label='Drone Flight Path')
    
    plt.title(f'2D Interpolated RF Heatmap: {ap_name}')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close() # Free up memory
    print(f"  [+] 2D Heatmap saved to: {output_path}")

def create_3d_surface_plot(grid_x, grid_y, grid_z, ap_name, output_path):
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    surf = ax.plot_surface(grid_x, grid_y, grid_z, 
                           cmap=CONFIG['visualization_params']['color_map'], 
                           alpha=CONFIG['visualization_params']['alpha'],
                           linewidth=0, antialiased=True)
    
    fig.colorbar(surf, shrink=0.5, aspect=5, label='RSSI (dBm)')
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.set_zlabel('Signal strength (dBm)')
    plt.title(f'3D Spatial RF Surface Plot: {ap_name}')
    
    plt.savefig(output_path, dpi=300)
    plt.close() # Free up memory
    print(f"  [+] 3D Surface Plot saved to: {output_path}")

def main(input_path, output_prefix):
    try:
        print(f"[*] Processing {input_path}...")
        
        # Pandas easily handles the mixed string/float columns
        df = pd.read_csv(input_path)
        
        if df.empty:
            print("[!] CSV is empty.")
            return

        # Fallback if testing with older CSVs that lack the AP_Label column
        if 'AP_Label' not in df.columns:
            df['AP_Label'] = 'Unknown_Target'

        # Group data by each unique Access Point found in the scan
        grouped_aps = df.groupby('AP_Label')
        print(f"[*] Found {len(grouped_aps)} unique Access Point(s) in the data.")

        for ap_name, group_data in grouped_aps:
            print(f"[*] Generating visuals for AP: {ap_name}")
            
            x = group_data['Longitude'].values
            y = group_data['Latitude'].values
            z = group_data['RSSI_dBm'].values
            
            # If the drone didn't move enough to interpolate, skip to avoid crashes
            if len(np.unique(x)) < 3 or len(np.unique(y)) < 3:
                print(f"  [!] Not enough spatial variance to interpolate {ap_name}. Skipping.")
                continue

            grid_x, grid_y, grid_z = generate_heatmap(x, y, z)

            # Generate dynamic filenames based on the AP name
            safe_ap_name = str(ap_name).replace(" ", "_")
            path_2d = f"{output_prefix}_{safe_ap_name}_2D.png"
            path_3d = f"{output_prefix}_{safe_ap_name}_3D.png"

            plot_2d_heatmap(grid_x, grid_y, grid_z, x, y, ap_name, path_2d)
            create_3d_surface_plot(grid_x, grid_y, grid_z, ap_name, path_3d)

    except Exception as e:
        print(f'[!] Error processing file: {str(e)}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate heatmaps from AP data.')
    parser.add_argument('--input', type=str, required=True, help='Input CSV data file path')
    parser.add_argument('--output', type=str, required=True, help='Output prefix (e.g., "scan_results")')
    args = parser.parse_args()
    main(args.input, args.output)
