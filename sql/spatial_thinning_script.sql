WITH filtered_data AS (
  SELECT 
    family, genus, species, decimallatitude, decimallongitude, year,individualcount, countrycode, elevation, elevationaccuracy,
    -- Pre-calculate the grid cell as a string to bypass the FLOAT64 partition restriction
    CONCAT(
      CAST(ROUND(decimallatitude, 1) AS STRING), 
      ',', 
      CAST(ROUND(decimallongitude, 1) AS STRING)
    ) AS grid_cell
  FROM
    `geo-global-ecosystems-atlas.gbif.gbif_2016-2026_plant_elv_basisofrec`
  WHERE 
    decimallatitude IS NOT NULL 
    AND decimallongitude IS NOT NULL
),
spatial_grid AS (
  SELECT *,
    -- Partitioning by the string 'grid_cell' is fully supported and highly efficient
    ROW_NUMBER() OVER(PARTITION BY species, grid_cell ORDER BY year DESC) as rn
  FROM filtered_data
)
-- Keep only the first record per species per grid cell
SELECT family, genus, species, decimallatitude, decimallongitude, year, individualcount, countrycode, elevation, elevationaccuracy
FROM spatial_grid
WHERE rn = 1
