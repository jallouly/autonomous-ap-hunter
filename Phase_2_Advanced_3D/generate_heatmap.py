import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import griddata
import plotly.graph_objects as go
import os

# 1. Setup Command Line Arguments
parser = argparse.ArgumentParser(description="Generate 3D RF Heatmaps for multiple Rogue APs")
parser.add_argument("--input", required=True, help="Input CSV file (e.g., rogue_ap_hunt.csv)")
parser.add_argument("--output", required=True, help="Output filename prefix (e.g., scan_results)")
args = parser.parse_args()

# 2. Load the telemetry data
print(f"[*] Loading flight data from {args.input}...")
try:
    df = pd.read_csv(args.input)
except FileNotFoundError:
    print(f"[!] Error: {args.input} not found. Did you fly the mission?")
    exit(1)

# 3. Find all unique MAC addresses discovered
unique_aps = df['AP_Label'].unique()
print(f"[*] Discovered {len(unique_aps)} unique Access Points!")

# 4. Generate Maps for EACH Access Point
for ap in unique_aps:
    print(f"  -> Generating spatial maps for MAC: {ap}...")
    
    ap_data = df[df['AP_Label'] == ap]
    
    if len(ap_data) < 5:
        print(f"     [!] Not enough data points to map {ap}. Skipping.")
        continue

    x = ap_data['Longitude'].values
    y = ap_data['Latitude'].values
    z = ap_data['RSSI_dBm'].values

    # Create a meshgrid for interpolation
    xi = np.linspace(x.min(), x.max(), 100)
    yi = np.linspace(y.min(), y.max(), 100)
    xi, yi = np.meshgrid(xi, yi)

    # Interpolate RSSI values across the grid
    zi = griddata((x, y), z, (xi, yi), method='cubic')
    
    safe_ap_name = ap.replace(":", "")

    # --- 2D HEATMAP (Standard PNG for READMEs) ---
    plt.figure(figsize=(10, 8))
    contour = plt.contourf(xi, yi, zi, levels=20, cmap='viridis')
    plt.colorbar(contour, label='RSSI (dBm)')
    plt.scatter(x, y, c='red', s=10, label='Drone Flight Path')
    
    max_idx = np.argmax(z)
    plt.scatter(x[max_idx], y[max_idx], c='gold', marker='*', s=300, edgecolor='black', label=f'Estimated Location ({z[max_idx]} dBm)')
    
    plt.title(f'2D RF Heatmap - Target: {ap}')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.legend()
    plt.savefig(f'{args.output}_{safe_ap_name}_2D.png')
    plt.close()

    # --- TRUE 3D INTERACTIVE FILE (Plotly HTML) ---
    fig = go.Figure(data=[go.Surface(z=zi, x=xi, y=yi, colorscale='Viridis', opacity=0.9)])
    
    # Add the drone's actual flight path as a red 3D line
    fig.add_trace(go.Scatter3d(x=x, y=y, z=z, mode='lines+markers', 
                               marker=dict(size=4, color='red'),
                               line=dict(color='red', width=2),
                               name='Flight Path'))

    fig.update_layout(title=f'Interactive 3D Signal Topology - MAC: {ap}',
                      autosize=True,
                      scene=dict(xaxis_title='Longitude',
                                 yaxis_title='Latitude',
                                 zaxis_title='RSSI (dBm)'))
    
    # Save as an interactive webpage!
    html_filename = f'{args.output}_{safe_ap_name}_3D_Interactive.html'
    fig.write_html(html_filename)
    print(f"     [+] Created interactive 3D file: {html_filename}")

print(f"\n[*] Mission Accomplished. All interactive 3D files saved with prefix '{args.output}'!")
