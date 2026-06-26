# GBIF Global Ecosystem Indicator Species Pipeline

This repository houses the automated data processing pipeline for filtering, classifying, and mapping global ecosystem indicator species for the EcoViewer. The workflow systematically processes raw biodiversity occurrence data and aligns it with the IUCN Global Ecosystem Typology through a series of spatial, environmental, and latitudinal constraints.

>  This repository demonstrates the backend data methodology powering the live EcoViewer application.

## ⚠️ Important Execution Note for Reviewers
While this codebase is provided under the MIT license to allow for a full technical review of our methodology, spatial joins, and processing logic, **these scripts cannot be executed directly in a local environment or third-party Google Earth Engine (GEE) Code Editor**. 

The pipeline relies on private lab environments, pre-computed spatial assets, and strict local directory structures. Attempting to run this code externally will result in "Asset Not Found" or path errors. To interact with the tool, run the species inspector, and generate regional CSVs, **please use the live application linked in our main submission.**

## 🌊 Pipeline Overview

The core objective of this pipeline is to reduce a massive dataset of global plant occurrences over the last 10 years down to a highly accurate subset of indicator species that obey defined physical and ecological boundaries. 

The pipeline handles:
1. Spatial thinning of dense occurrence records.
2. Ecosystem Functional Group (EFG) and Biome matching.
3. Masking of anthropogenic environments (Urban and Industrial Ecosystems, Plantations, and Croplands).
4. Latitudinal boundary enforcement (Tropical/Subtropical, Temperate, and Polar).
5. High-resolution environmental filtering using SRTM Elevation & Global Aridity Index.

## 💾 Dataset Citation & Processing Note
The initial raw dataset was sourced directly from GBIF: 
*GBIF.org (23 June 2026) GBIF Occurrence Download https://doi.org/10.15468/dl.sdhuv9*

However, to efficiently handle the massive scale of the initial occurrence data (~29 million records), the primary coordinate deduplication and spatial thinning steps were executed directly via **Google BigQuery using SQL**, rather than processing standard flat files locally.

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

* **`sql/`**: BigQuery SQL scripts used for the initial massive-scale spatial thinning and deduplication.
* **`js/`**: JavaScript code for Google Earth Engine (GEE) raster sampling and environmental extraction.
* **`src/` & Root**: Core executable Python processing scripts (`main.py`, `main_2.py`, `helper.py`). *(Note: Older methodology scripts are preserved in the `archive/` folders for version history).*
* **`data/`**: (GitIgnored) Local storage for raw and processed outputs.
* **`data/mapping/`**: Contains configuration files, metadata dictionaries, and the latest ecosystem indicator species list.
* **`data/outputs/`**: Contains plotted distributions before and after latitudinal correction.

---

## 🚀 Execution Steps

The logical flow of data through this repository follows a 5-step process:

1. **Raw Data Ingestion**: Secure raw GBIF occurrences via direct download and ingest into Google BigQuery.
2. **Spatial Thinning (`sql/`)**: Execute SQL queries to perform coordinate deduplication and baseline spatial thinning across the 29M record dataset.
3. **Indicator Matching (`main.py`)**: Run the primary Python script to align the thinned taxa against the latest ecosystem indicator species lists located in `data/mapping/`.
4. **Cloud Environmental Extraction (`js/`)**: Upload the intermediate dataset to GEE and execute `gbif_processing_T7_Elevation_AI.js` to sample SRTM Elevation, Aridity, and Anthropogenic footprints.
5. **Final Constraints & Formatting (`main_2.py`)**: Download the GEE-enriched outputs locally and execute `main_2.py` to enforce final latitudinal/altitude rules, apply taxonomic spot fixes, and export the publication-ready dataset.