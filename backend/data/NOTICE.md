# Landslide susceptibility data

`noah-landslide.pmtiles` contains the UP RI NOAH landslide susceptibility overlay used by GAKIT for Lanao del Norte and nearby areas.

Source: [UP RI NOAH](https://noah.upd.edu.ph/). Copied from GAKIT’s `lanao-del-norte-landslide.pmtiles` public map asset. Classification field: `LH` (1 low, 2 medium, 3 high). Preserve the original data provider’s terms and attribution; this repository does not grant a new license to the dataset.

The archive has limited geographic coverage. No mapped polygon at a location is not evidence of safety. Map display uses generalized tiles; point assessment uses the archive’s maximum zoom.

`noah-display.geojson` is a generalized derivative for map display: roughly 22 m vertex simplification, with fragments and holes below about 600 m² omitted. Do not use this layer for exact boundary assessment. Point queries use the original PMTiles archive.

The main application now streams the original PMTiles directly. The display GeoJSON remains only for the compatibility API.
