SELECT 
  family,
  genus,
  species,
  decimallatitude,
  decimallongitude,
  year,
  countrycode,
  individualcount,
  elevation,
  elevationaccuracy
FROM 
  `bigquery-public-data.gbif.occurrences`
WHERE 
  UPPER(kingdom) = 'PLANTAE' 
  AND year >= 2016 
  AND decimallatitude IS NOT NULL 
  AND decimallongitude IS NOT NULL
  AND `basisofrecord` IN ('HUMAN_OBSERVATION',
      'OBSERVATION',
      'OCCURRENCE')
      
