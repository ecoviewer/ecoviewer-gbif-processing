import os
import glob
import sys
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from datetime import datetime

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
REGION_NAME = "Global"  
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# --- Input Files (Post Earth Engine) ---
GEE_OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', 'GBIF_elv_ar_T7_raw_outputs')
BOUNDS_FILE = os.path.join(ROOT_DIR, 'data', 'mapping', 'latitudinal_bounds.txt')

# --- Output Directories ---
OUTPUT_FOLDER_NAME = f"{REGION_NAME}_Pipeline2_Final_{datetime.now().strftime('%Y%m%d')}"
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', OUTPUT_FOLDER_NAME)
PLOT_DIR = os.path.join(OUTPUT_DIR, 'plots')

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PLOT_DIR, exist_ok=True)

# --- Outputs ---
FINAL_CSV_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Fully_Masked.csv")
FINAL_FGB_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Fully_Masked.fgb")
AUDIT_CSV_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Pipeline2_Audit.csv")
SUMMARY_EFG_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Summary_EFG.csv")
PLOT_BEFORE = os.path.join(PLOT_DIR, 'Latitudinal_Before.png')
PLOT_AFTER = os.path.join(PLOT_DIR, 'Latitudinal_After.png')

# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================
audit_log = []

def record_audit(stage_name, current_df_length, details=""):
    """Tracks point counts, losses, and specific EFG alterations between stages."""
    if not audit_log:
        audit_log.append({"Stage": stage_name, "Remaining Points": current_df_length, "Points Lost": 0, "Details": details})
    else:
        lost = audit_log[-1]["Remaining Points"] - current_df_length
        audit_log.append({"Stage": stage_name, "Remaining Points": current_df_length, "Points Lost": lost, "Details": details})
    print(f" [Audit] {stage_name}: {current_df_length:,} points (Lost: {audit_log[-1]['Points Lost']:,})")

def parse_bounds(filepath):
    if not os.path.exists(filepath):
        sys.exit(f"Error: Bounds file not found at {filepath}")
    return {line.split(':')[0].strip(): float(line.split(':')[1].strip()) for line in open(filepath) if ':' in line}

def create_plot(df, title, filepath):
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].astype(str)
    masks = [df['Matching EFG, Biome'].str.startswith(x) | (df['Matching EFG, Biome'] == x) for x in ['T1.', 'T2.', 'T6.']]
    colors = ['#2ca02c', '#1f77b4', '#9467bd']
    titles = ['T1: Tropical Forests', 'T2: Temperate/Boreal', 'T6: Polar/Alpine']
    
    fig, axes = plt.subplots(3, 1, figsize=(12, 12), sharex=True)
    fig.suptitle(title, fontsize=18, fontweight='bold', y=0.95)
    
    for ax, m, c, t in zip(axes, masks, colors, titles):
        if m.sum() > 0:
            ax.hist(df[m]['decimallatitude'], bins=180, range=(-90, 90), color=c, edgecolor='black', linewidth=0.5)
        ax.set_title(f"{t} (n={m.sum():,})", fontsize=14)
        ax.set_ylabel('Frequency', fontsize=12)
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        
    axes[-1].set_xlabel('Latitude (Degrees)', fontsize=14)
    plt.xlim(-90, 90)
    plt.xticks(range(-90, 100, 10))
    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    plt.close()

# ==============================================================================
# 3. MAIN PIPELINE
# ==============================================================================
def run_pipeline_2():
    print("====================================================================")
    print("              STARTING PIPELINE 2: POST-EE PROCESSING               ")
    print("====================================================================\n")

    # --- STAGE 1: INGESTION ---
    print("--- STAGE 1: INGESTING EARTH ENGINE CHUNKS ---")
    chunk_files = glob.glob(os.path.join(GEE_OUTPUT_DIR, "GBIF_Combined_Masks_Chunk_*.csv"))
    
    if not chunk_files:
        sys.exit(f"Error: No chunk files found in {GEE_OUTPUT_DIR}.")
        
    print(f"Found {len(chunk_files)} chunk files. Compiling...")

    df_list = []
    for file_path in sorted(chunk_files):
        df_list.append(pd.read_csv(file_path))

    df = pd.concat(df_list, ignore_index=True)
    
    # Catch any coordinate variations (lat/decimallatitude) and standardize
    col_map = {c: 'decimallatitude' for c in df.columns if c.lower() in ['lat', 'decimallatitude', 'decimallat']}
    col_map.update({c: 'decimallongitude' for c in df.columns if c.lower() in ['long', 'lon', 'decimallongitude', 'decimallon']})
    df = df.rename(columns=col_map)

    if 'decimallatitude' not in df.columns or 'decimallongitude' not in df.columns:
        sys.exit("CRITICAL ERROR: Coordinates are missing. Ensure GEE export contained 'decimallatitude' and 'decimallongitude'.")

    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].astype(str)
    df['decimallatitude'] = pd.to_numeric(df['decimallatitude'], errors='coerce')
    df['decimallongitude'] = pd.to_numeric(df['decimallongitude'], errors='coerce')
    df = df.dropna(subset=['decimallatitude', 'decimallongitude'])
    
    record_audit("Initial Earth Engine Compilation", len(df), "Raw data loaded directly from chunks.")

    # --- STAGE 2: ANTHROPOGENIC MASKS ---
    print("\n--- STAGE 2: ANTHROPOGENIC MASKS ---")
    stage_2_details = []
    
    for col in ['Cropland', 'Plantation', 'Urban']:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)

    if 'Cropland' in df.columns:
        c_crop = (df['Cropland'] == 1).sum()
        df.loc[df['Cropland'] == 1, 'pixel value'] = '#FF14A1'
        if c_crop > 0: stage_2_details.append(f"Styled {c_crop:,} Cropland points")
        
    if 'Plantation' in df.columns:
        mask_plant = df['Plantation'] == 1
        c_plant = mask_plant.sum()
        df.loc[mask_plant, ['Matching EFG, Biome', 'pixel value']] = ['T7.3', '#AA005F']
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_plant, 'Matching EFG, Biome (full name)'] = 'Plantations'
        if c_plant > 0: stage_2_details.append(f"Converted {c_plant:,} points to T7.3")
            
    if 'Urban' in df.columns:
        mask_urban = df['Urban'] == 1
        c_urban = mask_urban.sum()
        df.loc[mask_urban, ['Matching EFG, Biome', 'pixel value']] = ['T7.4', '#8B0047']
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_urban, 'Matching EFG, Biome (full name)'] = 'Urban and industrial ecosystems'
        if c_urban > 0: stage_2_details.append(f"Converted {c_urban:,} points to T7.4")

    df = df.drop(columns=['Plantation', 'Urban', 'Cropland'], errors='ignore')
    record_audit("Applied Anthropogenic Overrides", len(df), "; ".join(stage_2_details))

    # --- STAGE 3: LATITUDINAL MASKS ---
    print("\n--- STAGE 3: LATITUDINAL MASKS ---")
    bounds = parse_bounds(BOUNDS_FILE)
    create_plot(df, 'BEFORE CORRECTION: Latitudinal Distribution', PLOT_BEFORE)
    
    stage_3_details = []
    df['latitudinal correction'] = False
    
    # Rule: Drop TF1.6 / TF1.7 inside Tropics
    is_tf = df['Matching EFG, Biome'].isin(['TF1.6', 'TF1.7'])
    lat = df['decimallatitude']
    mask_drop_tf = is_tf & (lat < bounds['Tropical North']) & (lat > bounds['Tropical South'])
    c_drop_tf = mask_drop_tf.sum()
    df = df[~mask_drop_tf].copy()
    if c_drop_tf > 0: stage_3_details.append(f"Dropped {c_drop_tf:,} TF1.6/TF1.7 inside tropics")

    lat = df['decimallatitude']
    is_t1 = df['Matching EFG, Biome'].str.startswith('T1.') | (df['Matching EFG, Biome'] == 'T1')
    is_t2 = df['Matching EFG, Biome'].str.startswith('T2.') | (df['Matching EFG, Biome'] == 'T2')
    is_t3 = df['Matching EFG, Biome'].str.startswith('T3.') | (df['Matching EFG, Biome'] == 'T3')
    is_t4 = df['Matching EFG, Biome'].str.startswith('T4.') | (df['Matching EFG, Biome'] == 'T4')

    # Overrides
    mask_r1 = is_t1 & ((lat > bounds['Tropical North']) | (lat < bounds['Tropical South']))
    c_r1 = mask_r1.sum()
    df.loc[mask_r1, ['Matching EFG, Biome', 'pixel value', 'latitudinal correction']] = ['T2', '#007767', True]
    if c_r1 > 0: stage_3_details.append(f"Converted {c_r1:,} T1 to T2")

    mask_r2 = is_t2 & (lat < bounds['Boreal N Close']) & (lat > bounds['Boreal S Close'])
    c_r2 = mask_r2.sum()
    df.loc[mask_r2, ['Matching EFG, Biome', 'pixel value', 'latitudinal correction']] = ['T1', '#008452', True]
    if c_r2 > 0: stage_3_details.append(f"Converted {c_r2:,} T2 to T1")

    mask_r4 = is_t2 & ((lat > bounds['Boreal N End']) | (lat < bounds['Boreal S End']))
    c_r4 = mask_r4.sum()
    df.loc[mask_r4, ['Matching EFG, Biome', 'pixel value', 'latitudinal correction']] = ['T6', '#D7D7D7', True]
    if c_r4 > 0: stage_3_details.append(f"Converted {c_r4:,} T2 to T6")

    mask_r5 = (is_t3 | is_t4) & ((lat > bounds['Polar North']) | (lat < bounds['Polar South']))
    c_r5 = mask_r5.sum()
    df.loc[mask_r5, ['Matching EFG, Biome', 'pixel value', 'latitudinal correction']] = ['T6', '#D7D7D7', True]
    if c_r5 > 0: stage_3_details.append(f"Converted {c_r5:,} T3/T4 to T6")
    
    create_plot(df, 'AFTER CORRECTION: Latitudinal Distribution', PLOT_AFTER)
    record_audit("Applied Latitudinal Overrides", len(df), "; ".join(stage_3_details))

    # --- STAGE 4: ELEVATION & ARIDITY MASKS ---
    print("\n--- STAGE 4: ELEVATION & ARIDITY MASKS ---")
    stage_4_details = []
    
    arid_col = 'aridity_index' if 'aridity_index' in df.columns else 'b1'
    if arid_col in df.columns:
        is_dry = df[arid_col] <= 300
        
        # 1. Identify groups allowed to survive completely unmodified (Added T6 to protect Polar regions)
        is_protected = (
            df['Matching EFG, Biome'].str.startswith('TF') | 
            df['Matching EFG, Biome'].str.startswith('T7') | 
            df['Matching EFG, Biome'].str.startswith('T6') | 
            (df['Matching EFG, Biome'] == 'T5.5')
        )
        
        # 2. Identify T5 groups targeted for desert classification conversion (excluding T5.5)
        is_any_t5 = df['Matching EFG, Biome'].str.startswith('T5.') | (df['Matching EFG, Biome'] == 'T5')
        is_convertible_t5 = is_any_t5 & (df['Matching EFG, Biome'] != 'T5.5')
        
        # Apply the conversion to valid desert elements within the dry threshold
        mask_t5_convert = is_dry & is_convertible_t5
        df.loc[mask_t5_convert, ['Matching EFG, Biome', 'pixel value']] = ['T5', '#DFB664']
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_t5_convert, 'Matching EFG, Biome (full name)'] = 'Deserts and semi-deserts'
        c_t5 = mask_t5_convert.sum()
        if c_t5 > 0: stage_4_details.append(f"Converted {c_t5:,} dry elements to T5")
        
        # Pull latitude to physically exempt polar zones from the hyper-arid drop rule
        lat_for_aridity = df['decimallatitude']
        in_polar_zone = (lat_for_aridity > bounds['Polar North']) | (lat_for_aridity < bounds['Polar South'])

        # 3. Drop any other non-applicable points within the dry mask (Excluding Polar points)
        mask_drop_dry = is_dry & (~is_protected) & (~is_convertible_t5) & (~in_polar_zone)
        c_drop_dry = mask_drop_dry.sum()
        df = df[~mask_drop_dry].copy()
        if c_drop_dry > 0: stage_4_details.append(f"Dropped {c_drop_dry:,} hyper-arid points")

    if 'elevation' in df.columns:
        elev, lat = pd.to_numeric(df['elevation'], errors='coerce'), df['decimallatitude']
        in_tropics = (lat <= bounds['Tropical North']) & (lat >= bounds['Tropical South'])
        
        # Rule A: T1.3 in tropics < 1300m -> Convert to T1.1
        mask_low = in_tropics & (df['Matching EFG, Biome'] == 'T1.3') & (elev < 1300)
        c_low = mask_low.sum()
        df.loc[mask_low, ['Matching EFG, Biome', 'pixel value']] = ['T1.1', '#32A06B']
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_low, 'Matching EFG, Biome (full name)'] = 'Tropical/Subtropical Lowland Rainforest'
        if c_low > 0: stage_4_details.append(f"Converted {c_low:,} low-elev T1.3 to T1.1")
            
        # Rule B: T1.3 in tropics >= 2308m -> Convert to T2
        mask_high = in_tropics & (df['Matching EFG, Biome'] == 'T1.3') & (elev >= 2308)
        c_high = mask_high.sum()
        df.loc[mask_high, ['Matching EFG, Biome', 'pixel value']] = ['T2', '#73D1BE']
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_high, 'Matching EFG, Biome (full name)'] = 'Warm Temperate Laurophyl Forests'
        if c_high > 0: stage_4_details.append(f"Converted {c_high:,} high-elev T1.3 to T2")
            
        # Rule C: T4 anywhere >= 2300m -> Convert to T6.4
        mask_t4 = (df['Matching EFG, Biome'].str.startswith('T4.') | (df['Matching EFG, Biome'] == 'T4')) & (elev >= 2300)
        c_t4 = mask_t4.sum()
        df.loc[mask_t4, ['Matching EFG, Biome', 'pixel value']] = ['T6.4', '#A8A8A8']
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_t4, 'Matching EFG, Biome (full name)'] = 'Temperate Alpine Grasslands and Shrubland'
        if c_t4 > 0: stage_4_details.append(f"Converted {c_t4:,} high-elev T4 to T6.4")

    # NOTE: T6.3 completely exempted from out-of-bounds dropping rules as requested.

    record_audit("Applied Elevation & Aridity Overrides", len(df), "; ".join(stage_4_details))

    # --- STAGE 5: SUMMARY & EXPORT ---
    print("\n--- STAGE 5: SUMMARY & EXPORT ---")
    
    # Save Audit Log
    pd.DataFrame(audit_log).to_csv(AUDIT_CSV_PATH, index=False)
    
    # Save EFG Summary
    df['Matching EFG, Biome'].value_counts().reset_index(name='Total_Points').rename(columns={'index': 'EFG'}).to_csv(SUMMARY_EFG_PATH, index=False)

    # Replicate Coordinate Geometries for downstream scripts
    df['lat'] = df['decimallatitude']
    df['long'] = df['decimallongitude']

    print("Converting to spatial format...")
    # Clean geometry assignment
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df['decimallongitude'], df['decimallatitude']),
        crs="EPSG:4326"
    )
    
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)

    print(f"Saving final CSV: {FINAL_CSV_PATH}")
    df.to_csv(FINAL_CSV_PATH, index=False)
    
    print(f"Saving final FlatGeobuf: {FINAL_FGB_PATH}")
    gdf.to_file(FINAL_FGB_PATH, driver='FlatGeobuf')
    
    print("\n====================================================================")
    print("                      PIPELINE 2 COMPLETE                           ")
    print("====================================================================")

if __name__ == "__main__":
    run_pipeline_2()