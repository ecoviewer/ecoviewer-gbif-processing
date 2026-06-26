/***************************************************************
 * gbif_processing_T7_Elevation_AI                             *
 *                                                             *
 * Script to merge SRTM Elevation, global Aridity Index values *              
 * cropland data from Copernicus_LCM_10m, urban layers from    *
 * dynamic world and forest typology 2020 plantation dataset   *
 * to prepare the final gbif data masks                        *
 *                                                             *
 * Authors: Dhruv Narayan, Ben Steer                           *
 *                                                             *
 *                                                             *
 * Last Updated:- 26-06-2026                                   *                    
 *                                                             *
 * James Cook University — Global Ecology Lab                  *
 ***************************************************************/




// ==============================================================================
// 1. ASSET CONFIGURATION
// ==============================================================================

// Load your Pipeline 1 Output points

// --- Anthropogenic Rasters ---
// Global cropland (VITO)
var cropRaster = ee.Image("projects/geo-global-ecosystems-atlas/assets/source_datasets/data_catalogue/396_vito_global_lcov_2025/Copernicus_LCM-10m-MERGED");
var cropland = cropRaster.eq(1).unmask(0).rename('Cropland');

// Global plantation (Nature-Trace)
var forestTypology = ee.ImageCollection("projects/nature-trace/assets/forest_typology/forest_typology_2020_v1_0_classification").mosaic();
var plantation = forestTypology.eq(3)
  .or(forestTypology.eq(4))
  .or(forestTypology.eq(5))
  .unmask(0)
  .rename('Plantation');

// Global urban areas (Dynamic World)
var urban = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
  .filterDate('2020-01-01', '2020-12-31')
  .select('label')
  .mode()
  .eq(6)
  .unmask(0)
  .rename('Urban');

// --- Environmental Rasters ---
// SRTM 30m Elevation
var elevation = ee.Image('USGS/SRTMGL1_003').select(['elevation'], ['elevation']);



// Merge all five layers into one single multi-band image
var combinedStack = ee.Image.cat([
  cropland,
  plantation,
  urban,
  elevation,
  aridity
]);

// ==============================================================================
// 3. DATASET CHUNKING & SAMPLING
// ==============================================================================

// Add a random column for clean partitioning
points = points.randomColumn('rand', 12345);

// --- THE FIX: Extract coordinates from the geometry and save them as standard properties ---
points = points.map(function(feature) {
  var coords = feature.geometry().coordinates();
  return feature.set({
    'decimallongitude': coords.get(0),
    'decimallatitude': coords.get(1)
  });
});

// Split into 10 batches to protect memory and EECUs
var nBatches = 10;
print('Total points queued for sampling:', points.size());

for (var i = 0; i < nBatches; i++) {

  // Filter the points for this specific chunk
  var batch = points.filter(
    ee.Filter.and(
      ee.Filter.gte('rand', i / nBatches),
      ee.Filter.lt('rand', (i + 1) / nBatches)
    )
  );

  // Extract all 5 values simultaneously
  var sampled = combinedStack.sampleRegions({
    collection: batch,
    scale: 30, // 30m is much safer for EECU billing than 10m
    geometries: false, // CRITICAL: Keeps memory low by dropping the heavy .geo column
    tileScale: 16 // Bumped to 16 to prevent memory crashes
  });

  // ==============================================================================
  // 4. EXPORT TO GOOGLE DRIVE
  // ==============================================================================
  
  Export.table.toDrive({
    collection: sampled,
    description: 'GBIF_Combined_Masks_Chunk_' + i,
    folder: 'Global_Ecosystems_Outputs_NEW', // Ensure this matches your Drive setup
    fileFormat: 'CSV'
  });
}