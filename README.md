# GeoSafe — Landslide Risk Mapper

A satellite-based landslide hotspot mapping prototype developed for the PhilSA Space Business Innovation Challenge 2025. GeoSafe combines vegetation change, a spectral moisture indicator, and terrain slope to highlight areas for further investigation.

## Features

- Compare historical and recent Sentinel-2 imagery within a configurable region and date range.
- Calculate NDVI vegetation change, NDWI, and SRTM-derived slope.
- Adjust risk weights and detection thresholds; inspect risk scores and hotspots on interactive maps.
- Export analysis layers as GeoTIFFs and download a ZIP with results and metadata.
- Explore simulated sensor nodes, readings, and data fusion in a proof-of-concept monitoring dashboard.

## Stack

Python, Streamlit, Google Earth Engine, Folium, geemap, NumPy, Pandas, Rasterio, and GeoPandas. See [requirements.txt](requirements.txt) for the dependency list.

## Run locally

```bash
git clone https://github.com/lstrjessh/PhilSA-GeoSafe-Landslide-Risk-Mapper.git
cd PhilSA-GeoSafe-Landslide-Risk-Mapper
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install dependencies and authenticate Earth Engine:

```bash
python -m pip install -r requirements.txt
earthengine authenticate
```

Use an Earth Engine-enabled Google Cloud project accessible to your account. Update `projects_to_try` in [utils/earth_engine_utils.py](utils/earth_engine_utils.py) to include your project ID; the checked-in ID is specific to the original environment.

```bash
streamlit run app.py
```

Open the local URL printed by Streamlit. Configure the region, comparison dates, weights, and thresholds in the sidebar, then run the analysis.

## Repository layout

```text
app.py                       Application and analysis workflow
requirements.txt             Python dependencies
utils/
  earth_engine_utils.py      Authentication and satellite preprocessing
  risk_calculation.py        Weighted risk scoring and hotspot detection
  visualization.py           Interactive map layers
  export_utils.py            GeoTIFF and ZIP export
  node_monitoring.py         Simulated sensors and data fusion
```

## Model and limitations

The risk score is a configurable weighted combination of vegetation loss, recent NDWI, and slope. Hotspots use a percentile threshold with a fallback. NDWI is a spectral moisture indicator, not a direct measurement of soil moisture.

Sensor readings and AI hybrid visualization are simulated proof-of-concept features. The repository references `app_demo.py`, but that file is not included. The primary entry point is `app.py`.

This is a research prototype; its outputs are not validated landslide forecasts or official hazard advisories. Satellite availability, cloud cover, date selection, and parameter choices affect the results.
