import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import os
import sys

# ================= CONFIGURATION =================
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# Input Paths
INPUT_CSV = os.path.join(ROOT_DIR, 'data', 'outputs', 'outputs_masked', 'Global_Final_with_Masks.csv')
BOUNDS_FILE = os.path.join(ROOT_DIR, 'data', 'mapping', 'latitudinal_bounds.txt')

# Output Paths
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', 'latitudinal_mask_outputs')
PLOT_DIR = os.path.join(OUTPUT_DIR, 'plots')

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

FINAL_OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'Global_Final_Latitudinal.csv')
FINAL_OUTPUT_FGB = os.path.join(OUTPUT_DIR, 'Global_Final_Latitudinal.fgb')
PLOT_BEFORE = os.path.join(PLOT_DIR, 'Latitudinal_Distribution_Before.png')
PLOT_AFTER = os.path.join(PLOT_DIR, 'Latitudinal_Distribution_After.png')
# =================================================

def parse_bounds(filepath):
    """Reads the latitudinal bounds text file into a dictionary."""
    if not os.path.exists(filepath):
        sys.exit(f"Error: Bounds file not found at {filepath}")
        
    bounds = {}
    with open(filepath, 'r') as f:
        for line in f:
            if ':' in line:
                key, val = line.split(':')
                bounds[key.strip()] = float(val.strip())
    return bounds

def create_distribution_plot(df, title, filepath):
    """Generates the stacked latitudinal histograms."""
    # Ensure strings to prevent regex errors
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].astype(str)

    mask_t1 = df['Matching EFG, Biome'].str.startswith('T1.') | (df['Matching EFG, Biome'] == 'T1')
    mask_t2 = df['Matching EFG, Biome'].str.startswith('T2.') | (df['Matching EFG, Biome'] == 'T2')
    mask_t6 = df['Matching EFG, Biome'].str.startswith('T6.') | (df['Matching EFG, Biome'] == 'T6')

    df_t1 = df[mask_t1]
    df_t2 = df[mask_t2]
    df_t6 = df[mask_t6]

    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)
    fig.suptitle(title, fontsize=18, fontweight='bold', y=0.95)

    bins = 180 
    lat_range = (-90, 90)

    axes[0].hist(df_t1['decimallatitude'], bins=bins, range=lat_range, color='#2ca02c', edgecolor='black', linewidth=0.5)
    axes[0].set_title(f'T1: Tropical-Subtropical Forests (n={len(df_t1):,})', fontsize=14)
    axes[0].set_ylabel('Frequency', fontsize=12)
    axes[0].grid(axis='y', linestyle='--', alpha=0.7)

    axes[1].hist(df_t2['decimallatitude'], bins=bins, range=lat_range, color='#1f77b4', edgecolor='black', linewidth=0.5)
    axes[1].set_title(f'T2: Temperate-Boreal Forests & Woodlands (n={len(df_t2):,})', fontsize=14)
    axes[1].set_ylabel('Frequency', fontsize=12)
    axes[1].grid(axis='y', linestyle='--', alpha=0.7)

    axes[2].hist(df_t6['decimallatitude'], bins=bins, range=lat_range, color='#9467bd', edgecolor='black', linewidth=0.5)
    axes[2].set_title(f'T6: Polar/Alpine (Cryogenic) Ecosystems (n={len(df_t6):,})', fontsize=14)
    axes[2].set_xlabel('Latitude (Degrees)', fontsize=14)
    axes[2].set_ylabel('Frequency', fontsize=12)
    axes[2].grid(axis='y', linestyle='--', alpha=0.7)

    plt.xlim(-90, 90)
    plt.xticks(range(-90, 100, 10))
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    plt.close()

def run_latitudinal_pipeline():
    print("1. Parsing Latitudinal Bounds...")
    bounds = parse_bounds(BOUNDS_FILE)
    print(f"  > Loaded {len(bounds)} boundaries.")

    print("\n2. Loading the merged global dataset...")
    df = pd.read_csv(INPUT_CSV)
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].astype(str)
    
    print("\n3. Generating 'BEFORE' plot...")
    create_distribution_plot(df, 'BEFORE CORRECTION: Global Latitudinal Distribution', PLOT_BEFORE)

    print("\n4. Applying Latitudinal Rules...")
    
    # Initialize the correction tracking column
    df['latitudinal correction'] = False
    
    # Pre-calculate base group masks so rules don't cascade and overwrite each other
    is_t1 = df['Matching EFG, Biome'].str.startswith('T1.') | (df['Matching EFG, Biome'] == 'T1')
    is_t2 = df['Matching EFG, Biome'].str.startswith('T2.') | (df['Matching EFG, Biome'] == 'T2')
    is_tf = df['Matching EFG, Biome'].isin(['TF1.6', 'TF1.7'])
    
    lat = df['decimallatitude']

    # --- RULE 3: Drop TF1.6 / TF1.7 if inside Tropics ---
    # Doing this first so we can completely drop the rows
    mask_drop_tf = is_tf & (lat < bounds['Tropical North']) & (lat > bounds['Tropical South'])
    drop_count = mask_drop_tf.sum()
    df = df[~mask_drop_tf].copy()
    print(f"  > Dropped {drop_count:,} TF1.6/TF1.7 points found inside the tropics.")

    # Re-establish Series references after dropping rows
    lat = df['decimallatitude']
    is_t1 = df['Matching EFG, Biome'].str.startswith('T1.') | (df['Matching EFG, Biome'] == 'T1')
    is_t2 = df['Matching EFG, Biome'].str.startswith('T2.') | (df['Matching EFG, Biome'] == 'T2')

    # --- RULE 1: T1 found outside Tropics -> Convert to T2 ---
    mask_r1 = is_t1 & ((lat > bounds['Tropical North']) | (lat < bounds['Tropical South']))
    df.loc[mask_r1, 'Matching EFG, Biome'] = 'T2'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_r1, 'Matching EFG, Biome (full name)'] = 'Temperate-Boreal Forests & Woodlands'
    df.loc[mask_r1, 'pixel value'] = '#007767'
    df.loc[mask_r1, 'latitudinal correction'] = True
    print(f"  > Converted {mask_r1.sum():,} out-of-bounds T1 points to T2.")

    # --- RULE 2: T2 found inside Tropics -> Convert to T1 ---
    # Using AND because it must be between the North Close and South Close lines
    mask_r2 = is_t2 & (lat < bounds['Boreal N Close']) & (lat > bounds['Boreal S Close'])
    df.loc[mask_r2, 'Matching EFG, Biome'] = 'T1'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_r2, 'Matching EFG, Biome (full name)'] = 'Tropical-subtropical forests'
    df.loc[mask_r2, 'pixel value'] = '#008452'
    df.loc[mask_r2, 'latitudinal correction'] = True
    print(f"  > Converted {mask_r2.sum():,} out-of-bounds T2 points to T1.")

    # --- RULE 4: T2 found in Polar regions -> Convert to T6 ---
    mask_r4 = is_t2 & ((lat > bounds['Boreal N End']) | (lat < bounds['Boreal S End']))
    df.loc[mask_r4, 'Matching EFG, Biome'] = 'T6'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_r4, 'Matching EFG, Biome (full name)'] = 'Polar/alpine (cryogenic)'
    df.loc[mask_r4, 'pixel value'] = '#D7D7D7'
    df.loc[mask_r4, 'latitudinal correction'] = True
    print(f"  > Converted {mask_r4.sum():,} out-of-bounds T2 points to T6.")

    print("\n5. Generating 'AFTER' plot...")
    create_distribution_plot(df, 'AFTER CORRECTION: Global Latitudinal Distribution', PLOT_AFTER)

    print("\n6. Converting to spatial format...")
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df['decimallongitude'], df['decimallatitude']),
        crs="EPSG:4326"
    )
    
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)

    print(f"\n7. Saving final outputs to {OUTPUT_DIR}...")
    df.to_csv(FINAL_OUTPUT_CSV, index=False)
    print(f"  > CSV Saved: {FINAL_OUTPUT_CSV}")

    gdf.to_file(FINAL_OUTPUT_FGB, driver='FlatGeobuf')
    print(f"  > FlatGeobuf Saved: {FINAL_OUTPUT_FGB}")
    
    print("\nPipeline Complete!")

if __name__ == "__main__":
    run_latitudinal_pipeline()