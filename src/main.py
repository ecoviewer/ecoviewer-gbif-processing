import pandas as pd
import bigframes.pandas as bpd
import geopandas as gpd
import os
import sys
from datetime import datetime

# ==============================================================================
# 1. CONFIGURATION (PIPELINE 1)
# ==============================================================================
REGION_NAME = "Global"  
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SRC_DIR)

# --- BigQuery Config ---
GCP_PROJECT_ID = "geo-global-ecosystems-atlas" 
GBIF_BQ_TABLE = "geo-global-ecosystems-atlas.gbif.gbif_2016-2026_basisofrec_spat_thinned" 

# --- Input Files ---
MAPPING_CSV = os.path.join(ROOT_DIR, 'data', 'mapping', 'eco_ind_sp_list_v2_230626.csv')

# --- Output Directories ---
OUTPUT_FOLDER_NAME = f"{REGION_NAME}_Pipeline1_Pre_EE_{datetime.now().strftime('%Y%m%d')}"
OUTPUT_DIR = os.path.join(ROOT_DIR, 'data', 'outputs', OUTPUT_FOLDER_NAME)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Outputs ---
FINAL_CSV_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Pre_EE_Mapped.csv")
FINAL_FGB_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Pre_EE_Mapped.fgb")
AUDIT_CSV_PATH = os.path.join(OUTPUT_DIR, f"{REGION_NAME}_Pipeline1_Audit.csv")

MIN_DECIMAL_PLACES = 3
audit_log = []

def record_audit(stage_name, current_df_length):
    if not audit_log:
        audit_log.append({"Stage": stage_name, "Remaining Points": current_df_length, "Points Lost": 0})
    else:
        lost = audit_log[-1]["Remaining Points"] - current_df_length
        audit_log.append({"Stage": stage_name, "Remaining Points": current_df_length, "Points Lost": lost})
    print(f" [Audit] {stage_name}: {current_df_length:,} points (Lost: {audit_log[-1]['Points Lost']:,})")

def load_and_clean_mapping(path):
    if not os.path.exists(path):
        sys.exit(f"Error: Mapping file not found at {path}")
    df = pd.read_csv(path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    col_map = {c: 'pixel value' for c in df.columns if c.lower() in ['pallete', 'palette', 'pixel value']}
    if col_map: df = df.rename(columns=col_map)
    df['Matching EFG, Biome'] = df['Matching EFG, Biome'].fillna('no value')
    df['pixel value'] = df['pixel value'].fillna('#FFFFFF')
    mask_empty = df['Matching EFG, Biome'].str.strip() == ''
    df.loc[mask_empty, ['Matching EFG, Biome', 'pixel value']] = ['no value', '#FFFFFF']
    df.loc[df['Matching EFG, Biome'] == 'no value', 'pixel value'] = '#FFFFFF'
    for col in ['Matching EFG, Biome', 'pixel value']:
        df[col] = df[col].astype(str).apply(lambda x: [i.strip() for i in x.split(',')] if x.strip() != '' else [])
        df = df.explode(col)
    return df

def run_pipeline_1():
    print("\n--- STAGE 1: CLOUD WATERFALL MATCHING ---")
    bpd.options.bigquery.project = GCP_PROJECT_ID
    
    gbif_df = bpd.read_gbq(GBIF_BQ_TABLE)
    mapping_df = bpd.DataFrame(load_and_clean_mapping(MAPPING_CSV)) 

    if 'species' in gbif_df.columns:
        gbif_df = gbif_df[~gbif_df['species'].str.lower().isin(['unknown', 'data deficient'])]

    lat_col, lon_col = 'decimallatitude', 'decimallongitude'
    gbif_df = gbif_df.dropna(subset=[lat_col, lon_col])
    
    lat_decimals = gbif_df[lat_col].astype(str).str.split('.').str[1]
    lon_decimals = gbif_df[lon_col].astype(str).str.split('.').str[1]
    gbif_df = gbif_df[(lat_decimals.str.len() >= MIN_DECIMAL_PLACES) & (lon_decimals.str.len() >= MIN_DECIMAL_PLACES)]

    if 'species' in gbif_df.columns:
        gbif_df['genus_extracted'] = gbif_df['species'].str.split(' ').str[0]
    
    final_matches = []

    for level in ['species', 'genus', 'family']:
        rules = mapping_df[mapping_df['Taxonomic Level'].str.lower() == level]
        if not rules.empty:
            match_col = 'genus_extracted' if level == 'genus' else level
            merged = gbif_df.merge(rules, left_on=match_col, right_on='Indicator', how='inner').to_pandas()
            if not merged.empty:
                final_matches.append(merged)
                gbif_df = gbif_df[~gbif_df[match_col].isin(rules['Indicator'])]

    if not final_matches: sys.exit("No matches found.")
    df = pd.concat(final_matches, ignore_index=True)
    record_audit("Raw Cloud Extraction", len(df))

    if 'individualcount' in df.columns:
        df['individualcount'] = pd.to_numeric(df['individualcount'], errors='coerce').fillna(1).astype(int).clip(upper=100)
        df = df.loc[df.index.repeat(df['individualcount'])].reset_index(drop=True)
        record_audit("Individual Count Expansion", len(df))

    df = df.drop_duplicates(subset=[lon_col, lat_col, 'Matching EFG, Biome'])
    record_audit("Removed Duplicate Coordinates", len(df))

    efg_counts = df.groupby([lon_col, lat_col])['Matching EFG, Biome'].nunique().reset_index()
    conflicting = efg_counts[efg_counts['Matching EFG, Biome'] > 1]
    df = df.merge(conflicting[[lon_col, lat_col]], on=[lon_col, lat_col], how='left', indicator=True)
    df = df[df['_merge'] == 'left_only'].drop(columns=['_merge', 'genus_extracted'], errors='ignore')
    record_audit("Removed Conflicting Pixels", len(df))

    # --- EARTH ENGINE PREP: Duplicate coordinates to bypass GEE geometry stripping ---
    print("\nDuplicating coordinates to 'lat' and 'long' for safe Earth Engine export...")
    df['lat'] = df[lat_col]
    df['long'] = df[lon_col]

    # Export
    pd.DataFrame(audit_log).to_csv(AUDIT_CSV_PATH, index=False)
    df.to_csv(FINAL_CSV_PATH, index=False)
    
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon_col], df[lat_col]), crs="EPSG:4326")
    for col in gdf.columns:
        if gdf[col].dtype == 'datetime64[ns]' or (not gdf[col].empty and isinstance(gdf[col].iloc[0], list)):
            gdf[col] = gdf[col].astype(str)
    gdf.to_file(FINAL_FGB_PATH, driver='FlatGeobuf')
    print(f"\nPipeline 1 Complete! Ready for Earth Engine upload: {FINAL_CSV_PATH}")

if __name__ == "__main__":
    run_pipeline_1()