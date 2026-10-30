"""Local, georeferenced exports and map previews for one analysis job."""

import csv
import hashlib
import json
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import array_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

PALETTES = {
    "risk_score": (0, 1, ["#f5f3df", "#e4ab50", "#a52a28"]),
    "hotspots": (0, 1, ["#a52a28", "#a52a28"]),
    "ndvi_change": (-0.4, 0.4, ["#b35806", "#f7f7f7", "#1b7837"]),
    "slope": (0, 60, ["#fff7ec", "#7f0000"]),
    "baseline_ndvi": (-1, 1, ["#b7c5c5", "#f4eed0", "#176036"]),
    "recent_ndvi": (-1, 1, ["#b7c5c5", "#f4eed0", "#176036"]),
}


def geotiff(values, grid):
    with rasterio.io.MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=1,
            dtype="float32",
            crs=grid["crs"],
            transform=grid["transform"],
            nodata=-9999.0,
            compress="deflate",
        ) as dataset:
            dataset.write(
                np.where(np.isfinite(values), values, -9999.0).astype("float32"), 1
            )
        return memory.read()


def preview(values, grid, name):
    extent = array_bounds(grid["height"], grid["width"], grid["transform"])
    transform, width, height = calculate_default_transform(
        grid["crs"], "EPSG:4326", grid["width"], grid["height"], *extent
    )
    raster = np.full((height, width), np.nan, dtype="float32")
    reproject(
        values,
        raster,
        src_transform=grid["transform"],
        src_crs=grid["crs"],
        src_nodata=np.nan,
        dst_transform=transform,
        dst_crs="EPSG:4326",
        dst_nodata=np.nan,
        resampling=Resampling.nearest,
    )
    low, high, colors = PALETTES[name]
    valid = np.isfinite(raster)
    if name == "hotspots":
        valid &= raster > 0
    scaled = np.clip((np.nan_to_num(raster, nan=low) - low) / (high - low), 0, 1)
    colors = np.array(
        [[int(color[i : i + 2], 16) for i in [1, 3, 5]] for color in colors]
    )
    rgba = np.zeros((height, width, 4), dtype="uint8")
    for channel in range(3):
        rgba[:, :, channel] = np.interp(
            scaled, np.linspace(0, 1, len(colors)), colors[:, channel]
        ).astype("uint8")
    rgba[:, :, 3] = np.where(valid, 210, 0)
    output = BytesIO()
    Image.fromarray(rgba).save(output, format="PNG")
    west, south, east, north = array_bounds(height, width, transform)
    return output.getvalue(), [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
    ]


def write_results(result, directory):
    directory.mkdir(parents=True, exist_ok=True)
    files = {}
    layers = []
    for name, values in result["images"].items():
        files[name + ".tif"] = geotiff(values, result["grid"])
        (directory / (name + ".tif")).write_bytes(files[name + ".tif"])
        png, coordinates = preview(values, result["grid"], name)
        (directory / (name + ".png")).write_bytes(png)
        layers.append({"id": name, "coordinates": coordinates})
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["longitude", "latitude", "risk_score", "hotspots", "ndvi_change", "slope"]
    )
    for feature in result["samples"]["features"]:
        writer.writerow(
            [
                *feature["geometry"]["coordinates"],
                *[
                    feature["properties"][k]
                    for k in ["risk_score", "hotspots", "ndvi_change", "slope"]
                ],
            ]
        )
    files["samples.csv"] = output.getvalue().encode()
    metadata = {
        **result["metadata"],
        "sha256": {
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()
        },
    }
    files["metadata.json"] = json.dumps(metadata, indent=2, allow_nan=False).encode()
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as zip_:
        for name, data in files.items():
            zip_.writestr(name, data)
    (directory / "analysis.zip").write_bytes(archive.getvalue())
    for name in ["samples.csv", "metadata.json"]:
        (directory / name).write_bytes(files[name])
    return {"metadata": metadata, "layers": layers, "samples": result["samples"]}
