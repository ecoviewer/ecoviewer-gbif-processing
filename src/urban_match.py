import pandas as pd
import geopandas as gpd
import glob
import os

# ================= CONFIGURATION =================
# 1. Get the absolute paths (This fixes the FileNotFoundError)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# 2. Path to your folder containing the 0-8 mask CSVs
MASK_FILES_PATTERN = os.path.join(ROOT_DIR, 'data', 'outputs', 'urban_mask', 'GBIF_Cropland_Plantation_Urban_*.csv')

# 3. Path to your original 1.5 million row dataset
ORIGINAL_DATA_CSV = os.path.join(ROOT_DIR, 'data', 'outputs', 'Global_Outputs_20260617_v2', 'Global_indicators_mapped_clean.csv') 

# 4. Create the new masked outputs folder
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', 'outputs_masked')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 5. Paths for the final merged outputs
FINAL_OUTPUT_CSV = os.path.join(OUTPUT_DIR, 'Global_Final_with_Masks.csv')
FINAL_OUTPUT_FGB = os.path.join(OUTPUT_DIR, 'Global_Final_with_Masks.fgb')
# =================================================
# =================================================

def run_merge_pipeline():
    print("1. Finding and loading the mask files...")
    
    mask_files = glob.glob(MASK_FILES_PATTERN)
    if not mask_files:
        raise FileNotFoundError(f"Could not find any files matching {MASK_FILES_PATTERN}")
    
    print(f"  > Found {len(mask_files)} files to concatenate.")

    # Read all CSVs using the column names as they exist in the mask files
    columns_to_keep = ['decimallat', 'decimallon', 'Cropland', 'Plantation', 'Urban']
    df_masks_list = [pd.read_csv(f, usecols=columns_to_keep) for f in mask_files]
    df_masks = pd.concat(df_masks_list, ignore_index=True)
    
    print("\n2. Renaming coordinate columns to match original dataset...")
    df_masks = df_masks.rename(columns={
        'decimallat': 'decimallatitude',
        'decimallon': 'decimallongitude'
    })

    # Drop any duplicate coordinates in the mask data
    df_masks = df_masks.drop_duplicates(subset=['decimallatitude', 'decimallongitude'])

    print("\n3. Loading the original dataset...")
    df_original = pd.read_csv(ORIGINAL_DATA_CSV)

    print("\n4. Merging the datasets on numeric coordinates...")
    df_final = df_original.merge(
        df_masks, 
        on=['decimallatitude', 'decimallongitude'], 
        how='left'
    )
    
    # Fill any unmatched rows with 0 for the binary columns 
    df_final[['Cropland', 'Plantation', 'Urban']] = df_final[['Cropland', 'Plantation', 'Urban']].fillna(0).astype(int)

    # =========================================================
    # STEP 5: ANTHROPOGENIC OVERRIDES 
    # =========================================================
    print("\n5. Applying Anthropogenic Overrides (Cropland, Plantation, Urban)...")

    # Rule 1: Cropland (Keep EFG, change color)
    mask_crop = df_final['Cropland'] == 1
    df_final.loc[mask_crop, 'pixel value'] = '#FF14A1'

    # Rule 2: Plantation (Overwrite EFG, Overwrite Name, Change color)
    mask_plant = df_final['Plantation'] == 1
    df_final.loc[mask_plant, 'Matching EFG, Biome'] = 'T7.3'
    if 'Matching EFG, Biome (full name)' in df_final.columns:
        df_final.loc[mask_plant, 'Matching EFG, Biome (full name)'] = 'Plantations'
    df_final.loc[mask_plant, 'pixel value'] = '#AA005F'

    # Rule 3: Urban (Overwrite EFG, Overwrite Name, Change color)
    mask_urban = df_final['Urban'] == 1
    df_final.loc[mask_urban, 'Matching EFG, Biome'] = 'T7.4'
    if 'Matching EFG, Biome (full name)' in df_final.columns:
        df_final.loc[mask_urban, 'Matching EFG, Biome (full name)'] = 'Urban and industrial ecosystems'
    df_final.loc[mask_urban, 'pixel value'] = '#8B0047'

    print(f"  > Overrides applied. Cleaning up columns...")
    
    # Drop the Plantation and Urban columns as requested
    df_final = df_final.drop(columns=['Plantation', 'Urban'])

    # =========================================================
    # STEP 6: SPATIAL CONVERSION & EXPORT
    # =========================================================
    print(f"\n6. Converting to spatial format...")
    
    # Create the GeoDataFrame
    gdf = gpd.GeoDataFrame(
        df_final, 
        geometry=gpd.points_from_xy(df_final['decimallongitude'], df_final['decimallatitude']),
        crs="EPSG:4326"
    )
    
    # Enforce string type on any list columns for database compliance
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)

    print(f"\n7. Saving final outputs to {OUTPUT_DIR}...")
    
    # Export CSV
    df_final.to_csv(FINAL_OUTPUT_CSV, index=False)
    print(f"  > CSV Saved: {FINAL_OUTPUT_CSV}")

    # Export FlatGeobuf
    gdf.to_file(FINAL_OUTPUT_FGB, driver='FlatGeobuf')
    print(f"  > FlatGeobuf Saved: {FINAL_OUTPUT_FGB}")
    
    print("\nDone! Pipeline complete.")

if __name__ == "__main__":
    run_merge_pipeline()