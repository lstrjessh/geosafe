"""Local reflectance GeoTIFF processing for users who already have prepared imagery."""

import hashlib
from datetime import datetime, timezone

import numpy as np
import rasterio

from .analysis import calculate, samples_for, weights_normalized
from .satellite import grid_for, index, read_band, slope_from_dem


def reflectance(path, grid):
    with rasterio.open(path) as source:
        if source.count < 3:
            raise ValueError(
                "Multispectral uploads require green, red, and NIR bands in that order."
            )
        scales, offsets = source.scales, source.offsets
        count = source.count
    bands = [
        read_band(path, grid, band=i + 1) * scales[i] + offsets[i] for i in range(3)
    ]
    valid = np.logical_and.reduce([np.isfinite(b) for b in bands])
    if count >= 4:
        # Optional fourth band: Sentinel scene classification (SCL).
        valid &= np.isin(read_band(path, grid, band=4, categorical=True), [4, 5, 6])
    for band in bands:
        values = band[valid]
        if len(values) and (np.nanmin(values) < -0.2 or np.nanmax(values) > 2):
            raise ValueError(
                "Upload surface reflectance in 0–1 units, or encode the correct scale and offset in the GeoTIFF metadata."
            )
    green, red, nir = [np.where(valid, b, np.nan) for b in bands]
    return index(nir, red), index(green, nir)


def run_uploaded(
    bounds,
    paths,
    weights,
    vegetation_threshold=0.2,
    water_threshold=0.1,
    percentile=90,
    progress=lambda text: None,
):
    grid = grid_for(bounds)
    progress("Reading uploaded baseline and recent imagery")
    baseline = reflectance(paths[0], grid)
    current = reflectance(paths[1], grid)
    progress("Reading uploaded elevation raster")
    slope = slope_from_dem(read_band(paths[2], grid), grid["resolution"])
    images, stats = calculate(
        current,
        baseline,
        slope,
        grid,
        weights,
        vegetation_threshold,
        water_threshold,
        percentile,
    )
    hashes = {}
    for name, path in zip(["baseline", "recent", "dem"], paths):
        hash_ = hashlib.sha256()
        with open(path, "rb") as file:
            while chunk := file.read(1024 * 1024):
                hash_.update(chunk)
        hashes[name] = hash_.hexdigest()
    return {
        "images": images,
        "grid": grid,
        "samples": samples_for(images, grid),
        "metadata": {
            **stats,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bounds": bounds,
            "analysis_scale_m": 30,
            "satellite_source": "User-supplied surface reflectance GeoTIFFs",
            "source_sha256": hashes,
            "cloud_mask": "Optional SCL fourth band; otherwise input must already be cloud-masked using nodata.",
            "weights": dict(
                zip(["vegetation_loss", "ndwi", "slope"], weights_normalized(weights))
            ),
            "vegetation_threshold": vegetation_threshold,
            "water_threshold": water_threshold,
            "interpretation": "Relative screening indicator, not a landslide probability or NOAH susceptibility class.",
        },
    }
