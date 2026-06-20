import pandas as pd
import geopandas as gpd
import os
import sys

# ================= CONFIGURATION =================
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# Input Paths 
INPUT_CSV = os.path.join(ROOT_DIR, 'data', 'outputs', 'GBIF_With_Elev_Aridity.csv')
BOUNDS_FILE = os.path.join(ROOT_DIR, 'data', 'mapping', 'latitudinal_bounds.txt')

# Output Paths
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', 'environment_mask_outputs_v6')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINAL_OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'global_gbif_v6.csv')
FINAL_OUTPUT_FGB = os.path.join(OUTPUT_DIR, 'global_gbif_v6.fgb')
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

def run_environment_pipeline():
    # Dictionary to track point removals for the final summary
    summary_stats = {
        'initial_points': 0,
        'dropped_aridity': 0,
        'dropped_gaultheria': 0,
        'final_points': 0
    }

    print("1. Parsing Latitudinal Bounds...")
    bounds = parse_bounds(BOUNDS_FILE)
    
    print("\n2. Loading the Earth Engine enriched dataset...")
    df = pd.read_csv(INPUT_CSV)
    summary_stats['initial_points'] = len(df)
    
    # Ensure strings to prevent matching errors
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].astype(str)

    # =========================================================
    # STEP 3: CONVERT .GEO TO LAT/LON
    # =========================================================
    print("\n3. Extracting coordinates from .geo column...")
    if '.geo' in df.columns:
        coords = df['.geo'].str.extract(r'\[(.*?),(.*?)\]')
        df['decimallongitude'] = coords[0].astype(float)
        df['decimallatitude'] = coords[1].astype(float)
        df = df.drop(columns=['.geo'])
        print("  > Successfully parsed coordinates and dropped .geo column.")
    else:
        print("  > Warning: .geo column not found. Continuing with existing coordinates.")

    # =========================================================
    # STEP 4: ARIDITY INDEX FILTERING (UPDATED)
    # =========================================================
    print("\n4. Applying Aridity Index Rules...")
    
    aridity_col = 'aridity_index'
    if 'b1' in df.columns:
        df = df.rename(columns={'b1': aridity_col})
    elif 'Aridity_Index' in df.columns:
        df = df.rename(columns={'Aridity_Index': aridity_col})
        
    if aridity_col in df.columns:
        is_dry = df[aridity_col] <= 300
        
        # 1. Identify groups allowed to survive completely unmodified
        is_protected = (
            df['Matching EFG, Biome'].str.startswith('TF') | 
            df['Matching EFG, Biome'].str.startswith('T7') | 
            (df['Matching EFG, Biome'] == 'T5.5')
        )
        
        # 2. Identify T5 groups targeted for desert classification conversion (excluding T5.5)
        is_any_t5 = df['Matching EFG, Biome'].str.startswith('T5.') | (df['Matching EFG, Biome'] == 'T5')
        is_convertible_t5 = is_any_t5 & (df['Matching EFG, Biome'] != 'T5.5')
        
        # Apply the conversion to valid desert elements within the dry threshold
        mask_t5_convert = is_dry & is_convertible_t5
        df.loc[mask_t5_convert, 'Matching EFG, Biome'] = 'T5'
        df.loc[mask_t5_convert, 'Matching EFG, Biome, Realm'] = 'Deserts and semi-deserts'
        df.loc[mask_t5_convert, 'pixel value'] = '#DFB664'
        print(f"  > Standardized {mask_t5_convert.sum():,} dry T5 sub-group points to the main Desert Biome.")
        
        # 3. Drop any other non-applicable points within the dry mask
        mask_to_drop = is_dry & (~is_protected) & (~is_convertible_t5)
        
        initial_count = len(df)
        df = df[~mask_to_drop].copy()
        summary_stats['dropped_aridity'] = initial_count - len(df)
        
        print(f"  > Dropped {summary_stats['dropped_aridity']:,} unmapped points found in hyper-arid zones.")
    else:
        print("  > Error: Aridity column not found! Skipping Aridity filter.")

    # =========================================================
    # STEP 5: ELEVATION & LATITUDINAL RULES
    # =========================================================
    print("\n5. Applying Elevation overrides...")
    
    lat = df['decimallatitude']
    elev = pd.to_numeric(df['elevation'], errors='coerce') 
    
    is_t13 = df['Matching EFG, Biome'] == 'T1.3'
    is_t4 = df['Matching EFG, Biome'].str.startswith('T4.') | (df['Matching EFG, Biome'] == 'T4')
    is_t63 = df['Matching EFG, Biome'] == 'T6.3'
    
    in_tropics = (lat <= bounds['Tropical North']) & (lat >= bounds['Tropical South'])

    # Rule A: T1.3 in tropics < 1300m -> Convert to T1.1
    mask_low = in_tropics & is_t13 & (elev < 1300)
    df.loc[mask_low, 'Matching EFG, Biome'] = 'T1.1'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_low, 'Matching EFG, Biome (full name)'] = 'Tropical/Subtropical Lowland Rainforest'
    df.loc[mask_low, 'pixel value'] = '#32A06B'
    print(f"  > Converted {mask_low.sum():,} low-elevation T1.3 points to T1.1.")

    # Rule B: T1.3 in tropics >= 2308m -> Convert to T2
    mask_high = in_tropics & is_t13 & (elev >= 2308)
    df.loc[mask_high, 'Matching EFG, Biome'] = 'T2'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_high, 'Matching EFG, Biome (full name)'] = 'Warm Temperate Laurophyl Forests'
    df.loc[mask_high, 'pixel value'] = '#73D1BE'
    print(f"  > Converted {mask_high.sum():,} high-elevation T1.3 points to T2.")

    # Rule C: T4 anywhere >= 2300m -> Convert to T6
    mask_t4_high = is_t4 & (elev >= 2300)
    df.loc[mask_t4_high, 'Matching EFG, Biome'] = 'T6'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_t4_high, 'Matching EFG, Biome (full name)'] = 'Polar/alpine (cryogenic)'
    df.loc[mask_t4_high, 'pixel value'] = '#D7D7D7'
    print(f"  > Converted {mask_t4_high.sum():,} high-elevation T4 points to T6.")

    # Rule D: T6.3 OUTSIDE polar bounds -> Convert to T6.4
    mask_t63_out = is_t63 & (lat > bounds['Polar South']) & (lat < bounds['Polar North'])
    df.loc[mask_t63_out, 'Matching EFG, Biome'] = 'T6.4'
    if 'Matching EFG, Biome (full name)' in df.columns:
        df.loc[mask_t63_out, 'Matching EFG, Biome (full name)'] = 'Temperate alpine grasslands and shrublands'
    df.loc[mask_t63_out, 'pixel value'] = '#A8A8A8'
    print(f"  > Converted {mask_t63_out.sum():,} out-of-bounds T6.3 points to T6.4.")

    # =========================================================
    # STEP 6: TAXONOMIC SPOT FIXES
    # =========================================================
    print("\n6. Applying Taxonomic Spot Fixes...")
    
    # 1. Avicennia marina override (Mangroves)
    if 'species' in df.columns:
        mask_avicennia = df['species'].astype(str).str.strip() == 'Avicennia marina'
        df.loc[mask_avicennia, 'Matching EFG, Biome'] = 'MFT1.2'
        if 'Matching EFG, Biome (full name)' in df.columns:
            df.loc[mask_avicennia, 'Matching EFG, Biome (full name)'] = 'Intertidal forests and shrublands'
        df.loc[mask_avicennia, 'pixel value'] = '#89474E'
        print(f"  > Mapped {mask_avicennia.sum():,} 'Avicennia marina' points to MFT1.2.")
    
    # 2. Gaultheria removal
    if 'genus' in df.columns:
        mask_gaultheria = df['genus'].astype(str).str.strip() == 'Gaultheria'
        summary_stats['dropped_gaultheria'] = mask_gaultheria.sum()
        df = df[~mask_gaultheria].copy()
        print(f"  > Dropped {summary_stats['dropped_gaultheria']:,} 'Gaultheria' points.")

    summary_stats['final_points'] = len(df)

    # =========================================================
    # STEP 7: FINAL REMOVAL SUMMARY
    # =========================================================
    print("\n" + "="*50)
    print(" PIPELINE REMOVAL SUMMARY")
    print("="*50)
    print(f" Initial Dataset Size:     {summary_stats['initial_points']:>10,}")
    print(f" Dropped (Aridity Filter): -{summary_stats['dropped_aridity']:>9,}")
    print(f" Dropped (Gaultheria):     -{summary_stats['dropped_gaultheria']:>9,}")
    print("-" * 50)
    print(f" FINAL RETAINED POINTS:    {summary_stats['final_points']:>10,}")
    print("="*50 + "\n")

    # =========================================================
    # STEP 8: EXPORT
    # =========================================================
    print(f"8. Duplicating coordinates and converting to spatial format...")
    
    df['lat'] = df['decimallatitude']
    df['long'] = df['decimallongitude']

    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df['decimallongitude'], df['decimallatitude']),
        crs="EPSG:4326"
    )
    
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)

    print(f"\nSaving final outputs to {OUTPUT_DIR}...")
    df.to_csv(FINAL_OUTPUT_CSV, index=False)
    print(f"  > CSV Saved: {FINAL_OUTPUT_CSV}")

    gdf.to_file(FINAL_OUTPUT_FGB, driver='FlatGeobuf')
    print(f"  > FlatGeobuf Saved: {FINAL_OUTPUT_FGB}")
    
    print("\nPipeline Complete!")

if __name__ == "__main__":
    run_environment_pipeline()