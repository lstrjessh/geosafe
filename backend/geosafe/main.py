"""GeoSafe API for a Vercel frontend and one Render worker."""

import json
import math
import os
import shutil
import tempfile
import threading
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import rasterio
from fastapi import FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pmtiles.reader import Reader
from pydantic import BaseModel, Field, model_validator
from rasterio.warp import transform
from shapely.geometry import box, mapping, shape
from shapely.strtree import STRtree

from . import jobs
from .analysis import run, weights_normalized
from .landslide import query_pmtiles, validate_bounds
from .observations import read_observations
from .satellite import grid_for
from .uploads import run_uploaded

app = FastAPI(title="GeoSafe", version="1.0.0")
origins = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip().rstrip("/") for o in origins if o.strip()],
    allow_methods=["GET", "HEAD", "POST"],
    allow_headers=["Content-Type", "Range", "If-Range"],
    expose_headers=["Accept-Ranges", "Content-Range", "Content-Length", "ETag"],
    allow_credentials=False,
)
ARCHIVE = Path(
    os.getenv(
        "GEOSAFE_LANDSLIDE_PMTILES",
        str(Path(__file__).resolve().parent.parent / "data/noah-landslide.pmtiles"),
    )
)
requests_by_ip = {}
polygon_lock = threading.Lock()


class AnalysisRequest(BaseModel):
    bounds: list[float] = Field(min_length=4, max_length=4)
    recent: tuple[date, date]
    historical: tuple[date, date]
    weights: list[float] = Field(default=[0.45, 0.35, 0.2], min_length=3, max_length=3)
    vegetation_threshold: float = Field(default=0.2, ge=0, le=0.8)
    water_threshold: float = Field(default=0.1, ge=0, le=0.6)
    percentile: int = Field(default=90, ge=75, le=99)
    cloud: int = Field(default=40, ge=0, le=100)

    @model_validator(mode="after")
    def valid(self):
        grid_for(self.bounds)
        weights_normalized(self.weights)
        if self.recent[0] > self.recent[1] or self.historical[0] > self.historical[1]:
            raise ValueError("Start dates must precede end dates.")
        if self.historical[1] >= self.recent[0]:
            raise ValueError("Baseline must end before the recent period begins.")
        if self.recent[1] > date.today():
            raise ValueError("Satellite periods cannot end in the future.")
        return self


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {
        "default_bounds": [124.20, 8.18, 124.28, 8.26],
        "susceptibility_available": ARCHIVE.is_file(),
        "landslide_archive": archive_info(ARCHIVE.stat().st_mtime_ns)
        if ARCHIVE.is_file()
        else None,
        "sources": {
            "susceptibility": "UP RI NOAH (LH 1/2/3)",
            "satellite": "Earth Search / Sentinel-2 L2A",
            "terrain": "Copernicus DEM GLO-30",
        },
        "analysis_resolution_m": 30,
        "max_analysis_pixels": 160000,
        "max_scenes_per_period": 4,
        "result_ttl_seconds": jobs.TTL,
    }


@lru_cache(maxsize=1)
def archive_info(modified):
    with ARCHIVE.open("rb") as file:

        def read(offset, length):
            file.seek(offset)
            return file.read(length)

        header = Reader(read).header()
    return {
        "url": "/api/landslide.pmtiles",
        "bounds": [
            header[key] / 1e7
            for key in ["min_lon_e7", "min_lat_e7", "max_lon_e7", "max_lat_e7"]
        ],
        "min_zoom": header["min_zoom"],
        "max_zoom": header["max_zoom"],
    }


@app.api_route("/api/landslide.pmtiles", methods=["GET", "HEAD"])
def landslide_archive():
    if not ARCHIVE.is_file():
        raise HTTPException(503, "Susceptibility archive is not configured.")
    return FileResponse(
        ARCHIVE,
        media_type="application/vnd.pmtiles",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@lru_cache(maxsize=1)
def display_shapes(modified):
    source = ARCHIVE.with_name("noah-display.geojson")
    data = json.loads(source.read_text(encoding="utf-8"))
    geometries, properties = [], []
    for feature in data["features"]:
        geometry = shape(feature["geometry"])
        parts = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
        for part in parts:
            geometries.append(part)
            properties.append(feature["properties"])
    return STRtree(geometries), geometries, properties


@lru_cache(maxsize=4)
def polygons(bounds, modified):
    region = box(*bounds)
    tree, geometries, properties = display_shapes(modified)
    features = []
    for index in tree.query(region):
        geometry = geometries[index]
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        clipped = geometry.intersection(region)
        if not clipped.is_empty:
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(clipped),
                    "properties": properties[index],
                }
            )
    return json.dumps(
        {"type": "FeatureCollection", "features": features}, separators=(",", ":")
    ).encode()


@app.get("/api/susceptibility")
def susceptibility(bounds: Annotated[str, Query(description="west,south,east,north")]):
    try:
        region = tuple(float(v) for v in bounds.split(","))
        validate_bounds(region)
        if not ARCHIVE.is_file():
            raise HTTPException(503, "Susceptibility archive is not configured.")
        with polygon_lock:
            content = polygons(
                region, ARCHIVE.with_name("noah-display.geojson").stat().st_mtime_ns
            )
        return Response(content, media_type="application/json")
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@lru_cache(maxsize=128)
def point_class(lat, lon, modified):
    return query_pmtiles(ARCHIVE, lat, lon)


@app.get("/api/assessment")
def assessment(lat: float = Query(ge=-85, le=85), lon: float = Query(ge=-180, le=180)):
    if not ARCHIVE.is_file():
        raise HTTPException(503, "Susceptibility archive is not configured.")
    level = point_class(lat, lon, ARCHIVE.stat().st_mtime_ns)
    return {
        "latitude": lat,
        "longitude": lon,
        "level": level,
        "source": "UP RI NOAH",
        "interpretation": "Mapped susceptibility, not current landslide activity. No mapped class does not establish safety.",
    }


@app.post("/api/analysis", status_code=202)
def start_analysis(body: AnalysisRequest, request: Request):
    now = time.monotonic()
    ip = request.client.host if request.client else "unknown"
    # Bound both compute concurrency and repeated public submissions.
    for key, seen in list(requests_by_ip.items()):
        if now - seen > 60:
            requests_by_ip.pop(key, None)
    if ip in requests_by_ip and now - requests_by_ip[ip] < 10:
        raise HTTPException(429, "Wait a few seconds before starting another analysis.")
    values = body.model_dump()
    values["recent"] = [d.isoformat() for d in body.recent]
    values["historical"] = [d.isoformat() for d in body.historical]
    try:
        id_ = jobs.create(lambda progress: run(**values, progress=progress))
    except RuntimeError as error:
        raise HTTPException(429, str(error)) from error
    requests_by_ip[ip] = now
    return {"id": id_, "status": "queued"}


@app.get("/api/analysis/{id_}")
def analysis_status(id_: str):
    job = jobs.get(id_)
    if not job:
        raise HTTPException(
            404,
            "Analysis not found or expired. Run it again; jobs also expire when the server restarts.",
        )
    return job


@app.get("/api/analysis/{id_}/files/{name}")
def artifact(id_: str, name: str):
    if name not in {
        "analysis.zip",
        "metadata.json",
        "samples.csv",
        "risk_score.png",
        "hotspots.png",
        "ndvi_change.png",
        "slope.png",
        "baseline_ndvi.png",
        "recent_ndvi.png",
    }:
        raise HTTPException(404, "File not found.")
    job = jobs.get(id_)
    if not job or job["status"] != "succeeded":
        raise HTTPException(404, "Analysis not ready or expired.")
    file = jobs.ROOT / id_ / name
    if not file.is_file():
        raise HTTPException(404, "File not found.")
    media = (
        "image/png"
        if name.endswith(".png")
        else {
            "analysis.zip": "application/zip",
            "metadata.json": "application/json",
            "samples.csv": "text/csv",
        }[name]
    )
    return FileResponse(
        file,
        media_type=media,
        filename=name if not name.endswith(".png") else None,
        headers={"Cache-Control": "private, max-age=300"},
    )


@app.post("/api/observations")
async def observations(file: UploadFile):
    content = await file.read(2 * 1024 * 1024 + 1)
    try:
        return {"observations": read_observations(content)}
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(422, str(error)) from error
    finally:
        await file.close()


@app.post("/api/analysis-upload", status_code=202)
async def uploaded_analysis(
    baseline: UploadFile,
    recent: UploadFile,
    dem: UploadFile,
    bounds: str = Form(),
    weights: str = Form("[0.45,0.35,0.2]"),
    vegetation_threshold: float = Form(0.2, ge=0, le=0.8),
    water_threshold: float = Form(0.1, ge=0, le=0.6),
    percentile: int = Form(90, ge=75, le=99),
):
    directory = Path(tempfile.mkdtemp(prefix="geosafe-upload-"))
    submitted = False
    try:
        region = json.loads(bounds)
        parsed_weights = json.loads(weights)
        grid_for(region)
        weights_normalized(parsed_weights)
        paths = []
        for name, file in zip(["baseline", "recent", "dem"], [baseline, recent, dem]):
            path = directory / (name + ".tif")
            size = 0
            with path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 50 * 1024 * 1024:
                        raise ValueError("Each GeoTIFF must be smaller than 50 MB.")
                    output.write(chunk)
            if not size:
                raise ValueError("GeoTIFF uploads must not be empty.")
            with path.open("rb") as input_file:
                if input_file.read(4) not in (
                    b"II*\x00",
                    b"MM\x00*",
                    b"II+\x00",
                    b"MM\x00+",
                ):
                    raise ValueError(
                        "Upload genuine GeoTIFF files, not VRT or other formats."
                    )
            paths.append(path)

        def work(progress):
            try:
                return run_uploaded(
                    region,
                    paths,
                    parsed_weights,
                    vegetation_threshold,
                    water_threshold,
                    percentile,
                    progress=progress,
                )
            finally:
                shutil.rmtree(directory, ignore_errors=True)

        try:
            id_ = jobs.create(work)
        except RuntimeError as error:
            raise HTTPException(429, str(error)) from error
        submitted = True
        return {"id": id_, "status": "queued"}
    except (ValueError, TypeError) as error:
        raise HTTPException(422, str(error)) from error
    finally:
        for file in [baseline, recent, dem]:
            await file.close()
        if not submitted:
            shutil.rmtree(directory, ignore_errors=True)


@app.get("/api/analysis/{id_}/point")
def raster_point(
    id_: str, lat: float = Query(ge=-85, le=85), lon: float = Query(ge=-180, le=180)
):
    job = jobs.get(id_)
    if not job or job["status"] != "succeeded":
        raise HTTPException(404, "Analysis not ready or expired.")
    values = {}
    for name in [
        "risk_score",
        "hotspots",
        "ndvi_change",
        "slope",
        "baseline_ndvi",
        "recent_ndvi",
    ]:
        with rasterio.open(jobs.ROOT / id_ / (name + ".tif")) as raster:
            xs, ys = transform("EPSG:4326", raster.crs, [lon], [lat])
            row, col = raster.index(xs[0], ys[0])
            value = None
            if 0 <= row < raster.height and 0 <= col < raster.width:
                cell = next(raster.sample([(xs[0], ys[0])], masked=True))[0]
                if not getattr(cell, "mask", False) and math.isfinite(float(cell)):
                    value = float(cell)
            values[name] = value
    return {
        "latitude": lat,
        "longitude": lon,
        "values": values,
        "interpretation": "Pixel values at the selected coordinate. Null means outside coverage or masked data.",
    }
