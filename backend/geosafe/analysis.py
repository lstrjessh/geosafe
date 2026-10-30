"""Deterministic local indicators and provenance, independent of the web framework."""

import math
from datetime import datetime, timezone

import numpy as np
from rasterio.warp import transform

from .satellite import composite, grid_for, terrain


def weights_normalized(weights):
    if (
        len(weights) != 3
        or any(not math.isfinite(w) or w < 0 for w in weights)
        or sum(weights) <= 0
    ):
        raise ValueError("At least one analysis weight must be positive.")
    return [w / sum(weights) for w in weights]


def calculate(
    current,
    baseline,
    slope,
    grid,
    weights,
    vegetation_threshold=0.2,
    water_threshold=0.1,
    percentile=90,
):
    weights = weights_normalized(weights)
    ndvi, ndwi = current
    old_ndvi, old_ndwi = baseline
    domain = grid.get("domain_mask", np.ones(ndvi.shape, dtype=bool))
    valid = (
        domain
        & np.isfinite(ndvi)
        & np.isfinite(old_ndvi)
        & np.isfinite(ndwi)
        & np.isfinite(old_ndwi)
        & np.isfinite(slope)
        & (old_ndvi > vegetation_threshold)
        & (ndwi <= water_threshold)
        & (old_ndwi <= water_threshold)
    )
    if not valid.any():
        raise ValueError(
            "No valid analysis pixels remain after cloud, water, vegetation, and terrain masking."
        )
    # Historical vegetation is the reference: complete vegetation loss stays visible.
    loss = np.clip((old_ndvi - ndvi) / 0.4, 0, 1)
    moisture = np.clip(ndwi / 0.6, 0, 1)
    steepness = np.clip((slope - 5) / 40, 0, 1)
    score = np.where(
        valid,
        loss * weights[0] + moisture * weights[1] + steepness * weights[2],
        np.nan,
    ).astype("float32")
    threshold = float(np.percentile(score[valid], percentile))
    hotspot = np.where(
        valid, ((score >= threshold) & (score > 0)).astype(float), np.nan
    ).astype("float32")
    change = np.where(valid, ndvi - old_ndvi, np.nan).astype("float32")
    valid_count = int(valid.sum())
    pixel_area = grid["resolution"] ** 2
    mean_old = float(old_ndvi[valid].mean())
    stats = {
        "score_threshold": threshold,
        "hotspot_percentile": percentile,
        "valid_pixels": valid_count,
        "coverage_percent": valid_count / int(domain.sum()) * 100,
        "valid_area_km2": valid_count * pixel_area / 1e6,
        "hotspot_area_km2": float(np.nansum(hotspot)) * pixel_area / 1e6,
        "hotspot_percent": float(np.nansum(hotspot)) / valid_count * 100,
        "mean_ndvi_change": float(change[valid].mean()),
        "score_distribution": {
            "edges": np.linspace(0, 1, 11).tolist(),
            "counts": np.histogram(score[valid], bins=np.linspace(0, 1, 11))[
                0
            ].tolist(),
        },
        "relative_ndvi_change_percent": float(change[valid].mean())
        / abs(mean_old)
        * 100
        if mean_old
        else None,
    }
    return {
        "risk_score": score,
        "hotspots": hotspot,
        "ndvi_change": change,
        "slope": np.where(valid, slope, np.nan).astype("float32"),
        "baseline_ndvi": np.where(domain, old_ndvi, np.nan).astype("float32"),
        "recent_ndvi": np.where(domain, ndvi, np.nan).astype("float32"),
    }, stats


def samples_for(images, grid, limit=180):
    rows, cols = np.where(np.isfinite(images["risk_score"]))
    # Evenly spaced actual valid raster cells, never synthetic observations.
    chosen = np.linspace(0, len(rows) - 1, min(limit, len(rows)), dtype=int)
    if not len(chosen):
        return {"type": "FeatureCollection", "features": []}
    xs, ys = [], []
    for i in chosen:
        t = grid["transform"]
        col, row = int(cols[i]) + 0.5, int(rows[i]) + 0.5
        x, y = t.a * col + t.b * row + t.c, t.d * col + t.e * row + t.f
        xs.append(x)
        ys.append(y)
    lons, lats = transform(grid["crs"], "EPSG:4326", xs, ys)
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    name: float(values[rows[i], cols[i]])
                    for name, values in images.items()
                },
            }
            for i, lon, lat in zip(chosen, lons, lats)
        ],
    }


def run(
    bounds,
    recent,
    historical,
    weights,
    vegetation_threshold=0.2,
    water_threshold=0.1,
    percentile=90,
    cloud=40,
    progress=lambda text: None,
):
    if historical[1] >= recent[0]:
        raise ValueError("The baseline must end before the recent period begins.")
    grid = grid_for(bounds)
    current_ndvi, current_ndwi, current_meta = composite(
        bounds, recent, grid, cloud, progress
    )
    old_ndvi, old_ndwi, old_meta = composite(bounds, historical, grid, cloud, progress)
    slope, dem_ids = terrain(bounds, grid, progress)
    images, stats = calculate(
        (current_ndvi, current_ndwi),
        (old_ndvi, old_ndwi),
        slope,
        grid,
        weights,
        vegetation_threshold,
        water_threshold,
        percentile,
    )
    return {
        "images": images,
        "grid": grid,
        "samples": samples_for(images, grid),
        "metadata": {
            **stats,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "bounds": bounds,
            "recent_period": recent,
            "historical_period": historical,
            "recent_source": current_meta,
            "baseline_source": old_meta,
            "terrain_source": {"collection": "cop-dem-glo-30", "items": dem_ids},
            "satellite_source": "Earth Search / Sentinel-2 L2A COGs",
            "analysis_scale_m": 30,
            "weights": dict(
                zip(["vegetation_loss", "ndwi", "slope"], weights_normalized(weights))
            ),
            "vegetation_threshold": vegetation_threshold,
            "water_threshold": water_threshold,
            "interpretation": "Relative satellite indicator score, not a NOAH susceptibility class, landslide probability, or event forecast.",
        },
    }
