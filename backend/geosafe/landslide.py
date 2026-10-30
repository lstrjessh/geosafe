"""NOAH susceptibility archives and location assessment, following GAKIT's LH codes."""

import gzip
import math
from pathlib import Path

import mapbox_vector_tile
import mercantile
from pmtiles.reader import Reader
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import transform

LEVELS = {1: "Low", 2: "Medium", 3: "High"}
COLORS = {1: "#FED7AA", 2: "#C2410C", 3: "#7C2D12"}


def validate_bounds(bounds):
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
        raise ValueError("Enter four finite region coordinates.")
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ValueError("West/south coordinates must be smaller than east/north.")
    area = (
        (east - west)
        * 111.32
        * math.cos(math.radians((south + north) / 2))
        * (north - south)
        * 111.32
    )
    if area > 400:
        raise ValueError(
            "Choose a region smaller than 400 km² for interactive analysis."
        )
    return area


def normalize_geojson(data):
    if data.get("type") != "FeatureCollection":
        raise ValueError(
            "Upload a GeoJSON FeatureCollection in WGS84 longitude/latitude."
        )
    features = []
    for feature in data.get("features", []):
        props = feature.get("properties") or {}
        value = props.get("LH")
        if isinstance(value, bool) or value not in (1, 2, 3):
            raise ValueError(
                "Every susceptibility polygon needs numeric LH = 1, 2, or 3."
            )
        geom = shape(feature.get("geometry") or {})
        if (
            geom.geom_type not in ("Polygon", "MultiPolygon")
            or geom.is_empty
            or not geom.is_valid
        ):
            raise ValueError("Susceptibility features must be valid polygons.")
        west, south, east, north = geom.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("GeoJSON coordinates must use WGS84 longitude/latitude.")
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {"LH": int(value)},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def query_geojson(data, lat, lon):
    point = Point(lon, lat)
    codes = [
        f["properties"]["LH"]
        for f in data["features"]
        if shape(f["geometry"]).covers(point)
    ]
    return LEVELS[max(codes)] if codes else None


def _tile_features(reader, header, tile):
    raw = reader.get(tile.z, tile.x, tile.y)
    if not raw:
        return []
    compression = header["tile_compression"].value
    if compression == 2:
        raw = gzip.decompress(raw)
    elif compression != 1:
        raise ValueError("This archive uses an unsupported tile compression.")
    layer = mapbox_vector_tile.decode(raw, default_options={"y_coord_down": True}).get(
        "landslide"
    )
    if not layer:
        raise ValueError("The archive must contain a landslide vector layer.")
    extent = layer.get("extent", 4096)

    def project(x, y, z=None):
        # Shapely may supply tuples; returning scalar coordinates triggers its scalar fallback.
        longitude = (tile.x + x / extent) / (2**tile.z) * 360 - 180
        latitude = math.degrees(
            math.atan(
                math.sinh(math.pi * (1 - 2 * (tile.y + y / extent) / (2**tile.z)))
            )
        )
        return longitude, latitude

    features = []
    tile_clip = box(*mercantile.bounds(tile))
    for f in layer["features"]:
        code = f.get("properties", {}).get("LH")
        if code not in LEVELS:
            continue
        geom = transform(project, shape(f["geometry"]))
        if not geom.is_valid:
            geom = geom.buffer(0)
        geom = geom.intersection(tile_clip)
        if not geom.is_empty:
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(geom),
                    "properties": {"LH": int(code)},
                }
            )
    return features


def read_pmtiles(path, bounds, point=False):
    """Read only intersecting tiles. Point queries always use native archive detail."""
    path = Path(path)
    with path.open("rb") as file:

        def read(offset, length):
            file.seek(offset)
            return file.read(length)

        reader = Reader(read)
        header = reader.header()
        if header["tile_type"].value != 1:
            raise ValueError("Select a vector PMTiles archive.")
        zoom = header["max_zoom"] if point else min(8, header["max_zoom"])
        tiles = list(mercantile.tiles(*bounds, zooms=zoom))
        if len(tiles) > 128:
            raise ValueError(
                "Region spans too many archive tiles. Select a smaller region."
            )
        features = []
        for tile in tiles:
            decoded = _tile_features(reader, header, tile)
            if point:
                features.extend(decoded)
            else:
                region = box(*bounds)
                for feature in decoded:
                    geom = (
                        shape(feature["geometry"])
                        .intersection(region)
                        .simplify(0.00008, preserve_topology=True)
                    )
                    if not geom.is_empty:
                        features.append({**feature, "geometry": mapping(geom)})
    return {"type": "FeatureCollection", "features": features}


def query_pmtiles(path, lat, lon):
    delta = 1e-8
    return query_geojson(
        read_pmtiles(
            path, [lon - delta, lat - delta, lon + delta, lat + delta], point=True
        ),
        lat,
        lon,
    )
