# Development

Use Python 3.12+ and Node.js 22.12+ (or Node.js 20.19+).

From the repository root:

```bash
python -m venv .venv
# Activate .venv using your shell.
python -m pip install -r backend/requirements-dev.txt
python -m uvicorn geosafe.main:app --app-dir backend --reload --port 8001
```

In a second terminal:

```bash
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open the Vite URL. Its development proxy forwards `/api` to port 8001.

Checks:

```bash
python -m pytest backend/tests -q
npm run build --prefix frontend
```

## Data and interpretation

NOAH susceptibility and satellite indicators are separate products. NOAH uses `LH` classes 1/2/3; no polygon means no mapped class, not safety. The map streams the original PMTiles archive using byte-range requests, selecting detail at the current zoom. Point lookup reads the same archive at its highest zoom. The generalized GeoJSON endpoint is retained for compatibility, but is no longer used for the main map.

Satellite inputs are up to four lowest-cloud Sentinel-2 L2A scenes per period from Earth Search. Reprocessed copies of a tile/day are deduplicated. Catalog scale/offset metadata is applied; only SCL 4/5/6 pixels are retained. Period composites use median indices. Coverage, failed scenes, and source IDs are recorded.

A local UTM grid at 30 m is used for alignment and area. Copernicus DEM supplies terrain; slope uses metric finite differences. The score combines normalized vegetation loss, NDWI, and slope using user-selected weights. Historically vegetated pixels remain eligible after recent vegetation loss. Water and missing observations are masked. Hotspots are relative to the selected percentile and must have a positive score. They are not landslide probabilities or forecasts.

## Local GeoTIFFs

Upload baseline and recent surface-reflectance rasters with bands ordered **green, red, NIR**, plus an elevation raster in metres. Reflectance must be in 0–1 units or have correct raster scale/offset metadata. Optional fourth band: Sentinel-2 SCL. Without SCL, the imagery must already be cloud-masked with nodata. Files need a CRS. Each file is limited to 50 MB.

## Sensor CSV

Required: `node_id,latitude,longitude,timestamp` and at least one sensor field. Timestamp must include `Z` or a timezone offset. Optional fields: `soil_moisture`, `tilt_x`, `tilt_y`, `tilt_z`, `vibration`, `temperature`, `humidity`, `pressure`. Soil moisture/humidity use percent; tilt uses degrees, temperature °C, pressure hPa. Duplicate node/timestamps, non-finite values, and impossible coordinates are rejected. Readings are displayed as measurements, not automatically certified hazard evidence.

## Runtime limits

One process runs one analysis at a time, with a queue of at most two jobs including the active job. Interactive analysis is bounded to 160,000 pixels (roughly 144 km² at 30 m). Results are temporary, expire after an hour, and become unavailable after a server restart. Use one instance/worker; multiple replicas need durable shared jobs and storage. Public cloud catalog requests can fail; failures remain explicit rather than returning fabricated data.

Downloads contain georeferenced float32 GeoTIFFs, CSV samples, and JSON metadata with file hashes. Nodata is preserved. PNG map previews have matching geographic bounds. The comparison uses the same NDVI scale and grid for both periods.
