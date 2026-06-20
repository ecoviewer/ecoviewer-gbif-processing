# GBIF Global Ecosystem Indicator Species Pipeline

This repository houses the automated data processing pipeline for filtering, classifying, and mapping global ecosystem indicator species for the EcoViewer. The workflow systematically processes raw biodiversity occurrence data and aligns it with the IUCN Global Ecosystem Typology through a series of spatial, environmental, and latitudinal constraints.

##  Pipeline Overview

The core objective of this pipeline is to reduce a raw GBIF dataset of global plant occourances for the last 10 years down to a highly accurate subset of indicator species that obey defined physical and ecological boundaries. 

The pipeline handles:
1. Spatial thinning of dense occurrence records.
2. Ecosystem Functional Group (EFG) and Biome matching.
3. Masking of anthropogenic environments. (Urban and Industrial Ecosystems, Plantations and Croplands)
4. Latitudinal boundary enforcement. (Tropical/Subtropical, Temperate and Polar)
5. High-resolution environmental filtering using SRTM Elevation & Aridity Index.

## 📊 Data Reduction Flowchart

```mermaid
graph TD
    A[Raw GBIF Data<br/>~29M Records] --> B(Spatial Thinning<br/>Deduplication & Gridding)
    B --> C(EFG Matching<br/>Align taxa to DB)
    
    C --> E(T7 Correction<br/>Drop Crop/Plant/Urban)
    
    E --> F[Latitudinal Masking]
    F -->|Tropics/Boreal/Polar| G{Latitude Rules}
    G -->|T1 out of bounds| H[To T2]
    G -->|T2 in Tropics| I[To T1]
    G -->|T2/T3/T4 in Polar| J[To T6]
    G -->|TF1.6/1.7 in Tropics| K[Drop]
    
    H & I & J & K --> L[Merged Dataset]
    
    L --> M[(GEE Cloud Extraction)]
    M -->|Scale: 30m| N(SRTM Elevation)
    M -->|Scale: 30m| O(Aridity Index)
    
    N & O --> P[Environmental Filter]
    P -->|AI <= 0.03| Q[Drop non-TF/T7]
    P -->|Elevation Rules| R{Altitude Rules}
    R -->|T1.3 < 1300m| S[To T1.1]
    R -->|T1.3 >= 2308m| T[To T2]
    R -->|T4 >= 2300m| U[To T6]
    R -->|T6.3 outside Polar| V[To T6.4]
    
    Q & S & T & U & V --> W[Taxonomic Fixes]
    W --> X(Avicennia to MFT1.2)
    W --> Y(Drop Gaultheria)
    
    X & Y --> Z([Final Dataset<br/>~1.5M Records])
    
    Z --> AA[Exports: CSV, FGB, FeatureView]
```

## 📁 Repository Structure

* `src/` - Contains all executable Python and sql processing scripts.
  * `urban_mask_merge.py` - Ingests and merges spatial mask chunks.
  * `latitudinal_mask.py` - Applies physical boundary constraints to EFGs.
  * `elevation_aridity_mask.py` - Enforces altitude and dryland survival rules.
* `data/` - (GitIgnored) Local storage for raw and processed outputs.
  * `mapping/` - Contains configuration files like `latitudinal_bounds.txt`.
  * `outputs/` - Contains intermediate CSVs and final FlatGeobuf files.

## 🚀 Execution Steps

To reproduce this pipeline from the raw datasets:

**Step 1: Local Masking & Latitudes**
1. Ensure the split mask CSVs are located in `data/outputs/urban_mask/`.
2. Run `python src/urban_mask_merge.py` to compile the baseline dataset.
3. Run `python src/latitudinal_mask.py` to enforce the physical biome boundaries.

**Step 2: Cloud Environmental Extraction**
1. Upload `Global_Final_Latitudinal.csv` to Google Cloud Storage / Earth Engine Assets.
2. Execute the GEE extraction script to sample SRTM Elevation and Aridity Index.
3. Export the resulting CSV back to your local environment.

**Step 3: Final Environmental Filtering**
1. Place the GEE-enriched CSV into `data/outputs/`.
2. Run `python src/elevation_aridity_mask.py`.
3. The final, publication-ready dataset will be generated in both `.csv` and `.fgb` formats.
