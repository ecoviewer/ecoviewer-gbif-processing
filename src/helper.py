import pandas as pd
import geopandas as gpd
import os

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# --- Input ---
INPUT_CSV = os.path.join(ROOT_DIR, 'data', 'outputs', 'Global_Final_Pipeline_20260623_temp', 'Global_GBIF_Fully_Masked.csv')

# --- Output ---
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', 'GBIF_v7')
os.makedirs(OUTPUT_DIR, exist_ok=True)

FINAL_CSV = os.path.join(OUTPUT_DIR, 'GBIF_v7.csv')
FINAL_FGB = os.path.join(OUTPUT_DIR, 'GBIF_v7.fgb')

# ==============================================================================
# 2. EXECUTION
# ==============================================================================
def run_v7_update():
    print(f"Loading data from: {INPUT_CSV}")
    df = pd.read_csv(INPUT_CSV)
    
    # ---------------------------------------------------------
    # SPOT FIX 1: T6.4 Overrides
    # ---------------------------------------------------------
    mask_t64 = df['Matching EFG, Biome'].astype(str).str.strip() == 'T6.4'
    df.loc[mask_t64, 'Matching EFG, Biome (full name)'] = 'Temperate alpine grasslands and shrublands'
    df.loc[mask_t64, 'pixel value'] = '#A8A8A8'
    print(f"Updated {mask_t64.sum():,} T6.4 records.")

    # ---------------------------------------------------------
    # SPOT FIX 2: Cropland Audit Flag
    # ---------------------------------------------------------
    # Initialize the column as completely False
    df['Falls on Cropland'] = False
    
    # Locate where the pixel is Cropland Pink (#FF14A1) but the EFG is NOT Cropland (T7.1)
    mask_cropland_conflict = (df['pixel value'] == '#FF14A1') & (df['Matching EFG, Biome'].astype(str).str.strip() != 'T7.1')
    
    # Flip those specific rows to True
    df.loc[mask_cropland_conflict, 'Falls on Cropland'] = True
    print(f"Flagged {mask_cropland_conflict.sum():,} records as 'Falls on Cropland = True'.")

    # ---------------------------------------------------------
    # SPOT FIX 3: T4 Pixel Override
    # ---------------------------------------------------------
    mask_t4 = df['Matching EFG, Biome'].astype(str).str.strip() == 'T4'
    df.loc[mask_t4, 'pixel value'] = '#FFC01C'
    print(f"Updated {mask_t4.sum():,} T4 records with pixel value #FFC01C.")

    # ---------------------------------------------------------
    # SPOT FIX 4: T3.4 Pixel Override
    # ---------------------------------------------------------
    mask_t34 = df['Matching EFG, Biome'].astype(str).str.strip() == 'T3.4'
    df.loc[mask_t34, 'pixel value'] = '#9AEAF1'
    print(f"Updated {mask_t34.sum():,} T3.4 records with pixel value #9AEAF1.")

    # ---------------------------------------------------------
    # SPOT FIX 5: T5.3 Pixel Override
    # ---------------------------------------------------------
    mask_t53 = df['Matching EFG, Biome'].astype(str).str.strip() == 'T5.3'
    df.loc[mask_t53, 'pixel value'] = '#B38E3E'
    print(f"Updated {mask_t53.sum():,} T5.3 records with pixel value #B38E3E.")

    # ---------------------------------------------------------
    # SPOT FIX 6: F2.8 Pixel Override
    # ---------------------------------------------------------
    mask_f28 = df['Matching EFG, Biome'].astype(str).str.strip() == 'F2.8'
    df.loc[mask_f28, 'pixel value'] = '#007A8A'
    print(f"Updated {mask_f28.sum():,} F2.8 records with pixel value #007A8A.")

    # ---------------------------------------------------------
    # SPOT FIX 7: F2.9 Pixel Override
    # ---------------------------------------------------------
    mask_f29 = df['Matching EFG, Biome'].astype(str).str.strip() == 'F2.9'
    df.loc[mask_f29, 'pixel value'] = '#005C6B'
    print(f"Updated {mask_f29.sum():,} F2.9 records with pixel value #005C6B.")

    # ---------------------------------------------------------
    # SPOT FIX 8: MASTER PALETTE CORRECTION
    # ---------------------------------------------------------
    print("\nEnforcing master hex codes from metadata.csv...")
    metadata_path = os.path.join(ROOT_DIR, 'data', 'mapping', 'metadata.csv')
    
    if os.path.exists(metadata_path):
        meta_df = pd.read_csv(metadata_path)
        
        # Clean whitespace to ensure perfect matching
        meta_df['EFG_Code'] = meta_df['EFG_Code'].astype(str).str.strip()
        meta_df['HexCode'] = meta_df['HexCode'].astype(str).str.strip()
        
        # Create lookup dictionary (EFG -> Hex)
        palette_map = dict(zip(meta_df['EFG_Code'], meta_df['HexCode']))
        
        # Cross-reference existing biomes with the expected hex codes
        expected_colors = df['Matching EFG, Biome'].astype(str).str.strip().map(palette_map)
        
        # Identify rows where the current color doesn't match the metadata
        mismatches = (df['pixel value'] != expected_colors) & expected_colors.notna()
        mismatch_count = mismatches.sum()
        
        if mismatch_count > 0:
            df.loc[mismatches, 'pixel value'] = expected_colors[mismatches]
            print(f"Fixed {mismatch_count:,} incorrect hex codes using metadata.csv.")
        else:
            print("All hex codes are already perfectly matched!")
    else:
        print(f"Warning: metadata.csv not found at {metadata_path}. Skipping palette fix.")

    # ---------------------------------------------------------
    # EXPORT
    # ---------------------------------------------------------
    # Save CSV
    print(f"\nSaving CSV: {FINAL_CSV}")
    df.to_csv(FINAL_CSV, index=False)
    
    # Save FGB
    print("Converting to spatial format for FGB export...")
    gdf = gpd.GeoDataFrame(
        df, 
        geometry=gpd.points_from_xy(df['decimallongitude'], df['decimallatitude']),
        crs="EPSG:4326"
    )
    
    # Clean lists/datetimes for FGB compatibility
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)
            
    print(f"Saving FGB: {FINAL_FGB}")
    gdf.to_file(FINAL_FGB, driver='FlatGeobuf')
    
    print("\nDONE! v7 files are ready.")

if __name__ == "__main__":
    run_v7_update()