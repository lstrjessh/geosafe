"""Public STAC discovery and bounded COG reads. No Earth Engine or cloud credentials."""

import json
import math
import warnings
from datetime import date
from urllib.parse import urlparse

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds, transform_geom

from .landslide import validate_bounds

STAC = "https://earth-search.aws.element84.com/v1/search"
MAX_SCENES = 4
MAX_CELLS = 160_000


def grid_for(bounds, resolution=30):
    validate_bounds(bounds)
    west, south, east, north = bounds
    if south < -80 or north > 84:
        raise ValueError(
            "Satellite analysis supports the UTM latitude range, 80°S to 84°N."
        )
    zone = min(60, max(1, int(((west + east) / 2 + 180) // 6) + 1))
    crs = f"EPSG:{32600 + zone if (south + north) / 2 >= 0 else 32700 + zone}"
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", crs, *bounds, densify_pts=21
    )
    width, height = (
        math.ceil((right - left) / resolution),
        math.ceil((top - bottom) / resolution),
    )
    if width < 3 or height < 3 or width * height > MAX_CELLS:
        raise ValueError(
            "Select a region between 3 x 3 pixels and 144 km² at 30 m resolution."
        )
    projected_region = transform_geom(
        "EPSG:4326",
        crs,
        {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        },
    )
    domain = geometry_mask(
        [projected_region],
        out_shape=(height, width),
        transform=from_origin(left, top, resolution, resolution),
        invert=True,
    )
    return {
        "domain_mask": domain,
        "crs": crs,
        "transform": from_origin(left, top, resolution, resolution),
        "width": width,
        "height": height,
        "resolution": resolution,
    }


def search(collection, bounds, period=None, cloud=None, limit=4):
    params = {
        "collections": collection,
        "bbox": ",".join(map(str, bounds)),
        "limit": limit,
    }
    if period:
        start, end = map(date.fromisoformat, period)
        if start > end:
            raise ValueError("Start dates must precede end dates.")
        params["datetime"] = (
            f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z"
        )
    if cloud is not None:
        params["query"] = json.dumps({"eo:cloud_cover": {"lte": cloud}})
        params["sortby"] = "properties.eo:cloud_cover"
    response = requests.get(STAC, params=params, timeout=(10, 45))
    response.raise_for_status()
    return response.json().get("features", [])[:limit]


def asset_url(asset):
    href = asset["href"]
    if href.startswith("s3://copernicus-dem-30m/"):
        href = href.replace(
            "s3://copernicus-dem-30m/",
            "https://copernicus-dem-30m.s3.amazonaws.com/",
            1,
        )
    parsed = urlparse(href)
    if parsed.scheme != "https" or parsed.hostname not in {
        "sentinel-cogs.s3.us-west-2.amazonaws.com",
        "copernicus-dem-30m.s3.amazonaws.com",
    }:
        raise ValueError("The catalog returned an unsupported raster source.")
    return href


def read_band(source, grid, band=1, categorical=False):
    # GDAL reads only the blocks intersecting this small projected window.
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_TIMEOUT="45",
        GDAL_HTTP_MAX_RETRY="2",
        GDAL_HTTP_RETRY_DELAY="1",
        VSI_CACHE="TRUE",
        VSI_CACHE_SIZE=4 * 1024 * 1024,
        GDAL_CACHEMAX=32 * 1024 * 1024,
    ):
        with rasterio.open(source) as dataset:
            if dataset.driver != "GTiff":
                raise ValueError("Only GeoTIFF raster inputs are supported.")
            if dataset.crs is None:
                raise ValueError(
                    "Input rasters must have a coordinate reference system."
                )
            if band > dataset.count:
                raise ValueError("Input raster does not contain the required bands.")
            with WarpedVRT(
                dataset,
                crs=grid["crs"],
                transform=grid["transform"],
                width=grid["width"],
                height=grid["height"],
                resampling=Resampling.nearest if categorical else Resampling.bilinear,
                dtype="float32",
                nodata=np.nan,
            ) as vrt:
                return vrt.read(band, masked=True).filled(np.nan)


def index(a, b):
    denominator = a + b
    valid = np.isfinite(a) & np.isfinite(b) & (a >= 0) & (b >= 0) & (denominator > 1e-6)
    out = np.full(a.shape, np.nan, dtype="float32")
    np.divide(a - b, denominator, out=out, where=valid)
    return np.clip(out, -1, 1)


def scene_indices(item, grid):
    assets = item["assets"]
    scl = read_band(asset_url(assets["scl"]), grid, categorical=True)
    clear = np.isin(scl, [4, 5, 6])
    bands = {}
    for name in ["green", "red", "nir"]:
        asset = assets[name]
        raster_meta = asset.get("raster:bands", [{}])[0]
        # Catalog offsets matter for post-2022 Sentinel-2 processing baselines.
        values = read_band(asset_url(asset), grid) * raster_meta.get(
            "scale", 1
        ) + raster_meta.get("offset", 0)
        bands[name] = np.where(clear, values, np.nan)
    return index(bands["nir"], bands["red"]), index(bands["green"], bands["nir"])


def composite(bounds, period, grid, cloud=40, progress=lambda text: None):
    candidates = search("sentinel-2-l2a", bounds, period, cloud, MAX_SCENES * 3)
    items = []
    seen = set()
    for item in candidates:
        key = (item["id"].split("_")[1], item["properties"].get("datetime", "")[:10])
        if key not in seen:
            seen.add(key)
            items.append(item)
        if len(items) >= MAX_SCENES:
            break
    if not items:
        raise ValueError(
            f"No Sentinel-2 scenes match {period}. Expand the dates or scene cloud limit."
        )
    ndvi, ndwi, used, failed = [], [], [], []
    for i, item in enumerate(items):
        progress(f"Reading Sentinel-2 scene {i + 1}/{len(items)} ({period[0]})")
        try:
            vegetation, moisture = scene_indices(item, grid)
        except (
            requests.RequestException,
            rasterio.errors.RasterioError,
            KeyError,
            ValueError,
        ) as error:
            failed.append({"id": item["id"], "error": str(error)[:300]})
            continue
        if np.isfinite(vegetation).any() and np.isfinite(moisture).any():
            ndvi.append(vegetation)
            ndwi.append(moisture)
            used.append(
                {
                    "id": item["id"],
                    "datetime": item["properties"].get("datetime"),
                    "cloud_cover": item["properties"].get("eo:cloud_cover"),
                }
            )
    if not used:
        raise ValueError(
            "No readable, clear Sentinel-2 pixels in this region and date range. Try wider dates or upload prepared rasters."
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return (
            np.nanmedian(ndvi, axis=0),
            np.nanmedian(ndwi, axis=0),
            {
                "scenes": used,
                "failed_scenes": failed,
                "selection": "Up to four lowest-cloud scenes returned by Earth Search; not all imagery in the interval.",
            },
        )


def terrain(bounds, grid, progress=lambda text: None):
    progress("Reading Copernicus DEM")
    items = search("cop-dem-glo-30", bounds, limit=9)
    elevation = np.full((grid["height"], grid["width"]), np.nan, dtype="float32")
    for item in items:
        values = read_band(asset_url(item["assets"]["data"]), grid)
        elevation = np.where(np.isfinite(elevation), elevation, values)
    if not np.isfinite(elevation).any():
        raise ValueError("No elevation coverage was found for this region.")
    return slope_from_dem(elevation, grid["resolution"]), [item["id"] for item in items]


def slope_from_dem(elevation, resolution):
    dy, dx = np.gradient(elevation, resolution, resolution)
    return np.degrees(np.arctan(np.hypot(dx, dy))).astype("float32")
