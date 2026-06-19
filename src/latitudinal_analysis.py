import pandas as pd
import matplotlib.pyplot as plt
import os

# ================= CONFIGURATION =================
# 1. Absolute Pathing
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# 2. Input and Output Paths
INPUT_CSV = os.path.join(ROOT_DIR, 'data', 'outputs', 'outputs_masked', 'Global_Final_with_Masks.csv')
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', 'plots')

# 3. Create the plots folder if it doesn't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 4. Final Image Path
OUTPUT_PNG = os.path.join(OUTPUT_DIR, 'Latitudinal_Distribution_T1_T2_T6.png')
# =================================================

def generate_latitudinal_histograms():
    print("1. Loading the masked global dataset...")
    # We only need two columns for this analysis to save memory
    df = pd.read_csv(INPUT_CSV, usecols=['decimallatitude', 'Matching EFG, Biome'])
    
    # Ensure it's a string to prevent regex errors
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].astype(str)

    print("2. Filtering the Biome groups (T1, T2, T6)...")
    # Exact matching: starts with 'T1.' OR is exactly 'T1'
    mask_t1 = df['Matching EFG, Biome'].str.startswith('T1.') | (df['Matching EFG, Biome'] == 'T1')
    mask_t2 = df['Matching EFG, Biome'].str.startswith('T2.') | (df['Matching EFG, Biome'] == 'T2')
    mask_t6 = df['Matching EFG, Biome'].str.startswith('T6.') | (df['Matching EFG, Biome'] == 'T6')

    df_t1 = df[mask_t1]
    df_t2 = df[mask_t2]
    df_t6 = df[mask_t6]

    print(f"  > Found {len(df_t1):,} T1 (Tropical) records.")
    print(f"  > Found {len(df_t2):,} T2 (Temperate/Boreal) records.")
    print(f"  > Found {len(df_t6):,} T6 (Polar/Alpine) records.")

    print("\n3. Generating Histograms...")
    # Create a figure with 3 subplots stacked vertically
    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)
    fig.suptitle('Global Latitudinal Distribution of Key Ecosystems', fontsize=18, fontweight='bold', y=0.95)

    # Use 180 bins so every bar represents exactly 1 degree of latitude
    bins = 180 
    lat_range = (-90, 90)

    # --- Plot T1: Tropical ---
    axes[0].hist(df_t1['decimallatitude'], bins=bins, range=lat_range, color='#2ca02c', edgecolor='black', linewidth=0.5)
    axes[0].set_title('T1: Tropical-Subtropical Forests', fontsize=14)
    axes[0].set_ylabel('Frequency (Data Points)', fontsize=12)
    axes[0].grid(axis='y', linestyle='--', alpha=0.7)

    # --- Plot T2: Temperate ---
    axes[1].hist(df_t2['decimallatitude'], bins=bins, range=lat_range, color='#1f77b4', edgecolor='black', linewidth=0.5)
    axes[1].set_title('T2: Temperate-Boreal Forests & Woodlands', fontsize=14)
    axes[1].set_ylabel('Frequency (Data Points)', fontsize=12)
    axes[1].grid(axis='y', linestyle='--', alpha=0.7)

    # --- Plot T6: Polar/Alpine ---
    axes[2].hist(df_t6['decimallatitude'], bins=bins, range=lat_range, color='#9467bd', edgecolor='black', linewidth=0.5)
    axes[2].set_title('T6: Polar/Alpine (Cryogenic) Ecosystems', fontsize=14)
    axes[2].set_xlabel('Latitude (Degrees)', fontsize=14)
    axes[2].set_ylabel('Frequency (Data Points)', fontsize=12)
    axes[2].grid(axis='y', linestyle='--', alpha=0.7)

    # Force the X-axis to lock between the South and North poles
    plt.xlim(-90, 90)
    
    # Add minor tick marks every 10 degrees for better readability
    plt.xticks(range(-90, 100, 10))

    # Adjust spacing
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    print(f"4. Saving high-resolution plot to {OUTPUT_PNG}...")
    plt.savefig(OUTPUT_PNG, dpi=300, bbox_inches='tight')
    plt.close()

    print("Done! Check your outputs/plots folder.")

if __name__ == "__main__":
    generate_latitudinal_histograms()