import pandas as pd
import bigframes.pandas as bpd
import geopandas as gpd
import os
import sys
from datetime import datetime

# ================= CONFIGURATION =================
REGION_NAME = "Global"  

# 1. PATH CONFIGURATION (Based on new repo structure)
# Assumes this script is running from inside the 'src/' folder
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# 2. BIGQUERY CONFIGURATION
GCP_PROJECT_ID = "geo-global-ecosystems-atlas" 
GBIF_BQ_TABLE = "geo-global-ecosystems-atlas.gbif.gbif_2016-2026_basisofrec_spat_thinned" 

# 3. LOCAL FILES
MAPPING_CSV = os.path.join(ROOT_DIR, 'data', 'mapping', 'eco_ind_sp_list_v2_230626.csv') #DN -- THIS SECTION IS CRITICAL AS WELL AS BIGQUERY CONFIG.

# 4. AUTO-FOLDER GENERATION
OUTPUT_FOLDER_NAME = f"{REGION_NAME}_Outputs_{datetime.now().strftime('%Y%m%d')}"
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', OUTPUT_FOLDER_NAME)
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_CSV_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_indicators_mapped_clean.csv")
OUTPUT_FGB_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_indicators_mapped_clean.fgb")

# 5. CLEANING PARAMETERS
MIN_DECIMAL_PLACES = 3

print(f"BigQuery Table: {GBIF_BQ_TABLE}")
print(f"Mapping Table:  {MAPPING_CSV}")
print(f"Output Folder:  {OUTPUT_DIR}")
# =================================================

def load_and_clean_mapping(path):
    """Loads mapping table locally, handles EFG/Biome defaults, and explodes lists."""
    if not os.path.exists(path):
        sys.exit(f"Error: Mapping file not found at {path}")
        
    df = pd.read_csv(path, dtype=str)
    
    # 1. Clean Headers
    df.columns = [c.strip() for c in df.columns]
    
    # 2. Normalize 'pixel value' (handles 'pallete' typo from your CSV)
    col_map = {c: 'pixel value' for c in df.columns if c.lower() in ['pallete', 'palette', 'pixel value']}
    if col_map:
        df = df.rename(columns=col_map)
    
    if 'Matching EFG, Biome' not in df.columns or 'pixel value' not in df.columns:
        sys.exit(f"Error: Mapping CSV missing required columns. Found: {list(df.columns)}")

    # 3. HANDLE MISSING VALUES
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].fillna('no value')
    df['pixel value'] = df['pixel value'].fillna('#FFFFFF')
    
    mask_empty = df['Matching EFG, Biome'].str.strip() == ''
    df.loc[mask_empty, 'Matching EFG, Biome'] = 'no value'
    df.loc[mask_empty, 'pixel value'] = '#FFFFFF'
    df.loc[df['Matching EFG, Biome'] == 'no value', 'pixel value'] = '#FFFFFF'

    # 4. SPLIT & EXPLODE
    target_cols = ['Matching EFG, Biome', 'pixel value']
    for col in target_cols:
        df[col] = df[col].astype(str).apply(lambda x: [i.strip() for i in x.split(',')] if x.strip() != '' else [])
    
    for col in target_cols:
        df = df.explode(col)
    
    print(f"Mapping Rules Loaded (Local): {len(df)} rows.")
    return df

def map_ecosystems_cloud():
    print("\n--- STARTING CLOUD WATERFALL MATCHING PIPELINE ---")
    
    # Authenticate BigFrames
    bpd.options.bigquery.project = GCP_PROJECT_ID

    # === STEP 1: LOAD DATA ===
    print("\n1. Connecting to Cloud Data...")
    gbif_df = bpd.read_gbq(GBIF_BQ_TABLE)
    
    local_mapping_df = load_and_clean_mapping(MAPPING_CSV)
    mapping_df = bpd.DataFrame(local_mapping_df) 

    # === STEP 2: CLOUD DATA SCREENING ===
    print("\n2. Executing Data Screening on BigQuery...")
        
    # Remove 'unknown' or 'data deficient' labels from taxonomy before analysis
    if 'species' in gbif_df.columns:
        gbif_df = gbif_df[~gbif_df['species'].str.lower().isin(['unknown', 'data deficient'])]

    # Coordinate Precision Filter using exact lowercase column names
    lat_col = 'decimallatitude'
    lon_col = 'decimallongitude'
    
    gbif_df = gbif_df.dropna(subset=[lat_col, lon_col])
    
    lat_decimals = gbif_df[lat_col].astype(str).str.split('.').str[1]
    lon_decimals = gbif_df[lon_col].astype(str).str.split('.').str[1]
    
    gbif_df = gbif_df[(lat_decimals.str.len() >= MIN_DECIMAL_PLACES) & (lon_decimals.str.len() >= MIN_DECIMAL_PLACES)]

    # === STEP 3: CLOUD WATERFALL MATCHING ===
    print("\n3. Matching Ecosystem Indicators (Running in Cloud)...")
    
    if 'species' in gbif_df.columns:
        gbif_df['genus_extracted'] = gbif_df['species'].str.split(' ').str[0]
    
    final_matches = []

    # Level 1: Species
    species_rules = mapping_df[mapping_df['Taxonomic Level'].str.lower() == 'species']
    if not species_rules.empty:
        merged_sp = gbif_df.merge(species_rules, left_on='species', right_on='Indicator', how='inner')
        local_sp = merged_sp.to_pandas()
        if not local_sp.empty:
            print(f"  > Level 1 (Species): Matched {len(local_sp):,} records")
            final_matches.append(local_sp)
            gbif_df = gbif_df[~gbif_df['species'].isin(species_rules['Indicator'])]

    # Level 2: Genus
    genus_rules = mapping_df[mapping_df['Taxonomic Level'].str.lower() == 'genus']
    if not genus_rules.empty:
        merged_gn = gbif_df.merge(genus_rules, left_on='genus_extracted', right_on='Indicator', how='inner')
        local_gn = merged_gn.to_pandas()
        if not local_gn.empty:
            print(f"  > Level 2 (Genus):   Matched {len(local_gn):,} records")
            final_matches.append(local_gn)
            gbif_df = gbif_df[~gbif_df['genus_extracted'].isin(genus_rules['Indicator'])]

    # Level 3: Family
    family_rules = mapping_df[mapping_df['Taxonomic Level'].str.lower() == 'family']
    if not family_rules.empty:
        merged_fm = gbif_df.merge(family_rules, left_on='family', right_on='Indicator', how='inner')
        local_fm = merged_fm.to_pandas()
        if not local_fm.empty:
            print(f"  > Level 3 (Family):  Matched {len(local_fm):,} records")
            final_matches.append(local_fm)

    if not final_matches:
        print("No matches found based on your indicators.")
        return

    result_df = pd.concat(final_matches, ignore_index=True)
    print(f"  > Total Mapped Occurrences Downloaded: {len(result_df):,}")

    # === STEP 4: INDIVIDUAL COUNT EXPANSION (LOCAL) ===
    print("\n4. Expanding Rows by Individual Count (Locally)...")
    if 'individualcount' in result_df.columns:
        result_df['individualcount'] = pd.to_numeric(result_df['individualcount'], errors='coerce').fillna(1).astype(int)
        result_df['individualcount'] = result_df['individualcount'].clip(upper=100)
        
        result_df = result_df.loc[result_df.index.repeat(result_df['individualcount'])].reset_index(drop=True)
        print(f"  > Expanded dataset to {len(result_df):,} total occurrences.")

    # === STEP 5: DATA PURITY FILTERING & EXPORT ===
    print(f"\n5. Filtering out GBIF coordinate stacks and exporting...")

    # 1. Deduplicate identical rows (same spot, same EFG match)
    initial_count = len(result_df)
    result_df = result_df.drop_duplicates(subset=[lon_col, lat_col, 'Matching EFG, Biome'])
    after_dedup = len(result_df)
    print(f"  > Removed {initial_count - after_dedup:,} duplicate rows at identical locations.")

    # 2. Identify coordinates mapping to MULTIPLE DIFFERENT ecosystem groups
    # Group by coordinates and count unique EFG values
    efg_counts = result_df.groupby([lon_col, lat_col])['Matching EFG, Biome'].nunique().reset_index()
    conflicting_coords = efg_counts[efg_counts['Matching EFG, Biome'] > 1]

    # Merge back to drop the conflicting locations entirely
    result_df = result_df.merge(
        conflicting_coords[[lon_col, lat_col]], 
        on=[lon_col, lat_col], 
        how='left', 
        indicator=True
    )
    result_df = result_df[result_df['_merge'] == 'left_only'].drop(columns=['_merge'])

    final_count = len(result_df)
    print(f"  > Dropped {after_dedup - final_count:,} rows due to conflicting ecosystem classifications at the same pixel.")
    print(f"  > Final clean record count: {final_count:,}")
    
    # Cleanup taxonomic helper columns before export
    if 'genus_extracted' in result_df.columns:
        result_df = result_df.drop(columns=['genus_extracted'])

    # 3. Convert to GeoDataFrame
    gdf = gpd.GeoDataFrame(
        result_df, 
        geometry=gpd.points_from_xy(result_df[lon_col], result_df[lat_col]),
        crs="EPSG:4326"
    )
    
    # Enforce string type on list columns and datetimes for database compliance
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)

    # 4. Save clean outputs
    print(f"\nSaving cleaned datasets to {OUTPUT_DIR}...")
    gdf.to_file(OUTPUT_FGB_PATH, driver='FlatGeobuf')
    print(f"  > FlatGeobuf Saved: {OUTPUT_FGB_PATH}")
    
    result_df.to_csv(OUTPUT_CSV_PATH, index=False)
    print(f"  > CSV Saved: {OUTPUT_CSV_PATH}")
    
    print(f"\n{'='*50}")
    print(" PIPELINE COMPLETE")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    map_ecosystems_cloud()