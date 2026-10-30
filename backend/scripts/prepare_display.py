"""Regenerate the generalized display derivative; point queries retain the original archive."""

import json
import sys
from pathlib import Path

from pmtiles.reader import Reader
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from geosafe.landslide import read_pmtiles  # noqa: E402


def main():
    archive = BASE / "data/noah-landslide.pmtiles"
    with archive.open("rb") as file:

        def read(offset, length):
            file.seek(offset)
            return file.read(length)

        header = Reader(read).header()
    bounds = [
        header[key] / 1e7
        for key in ["min_lon_e7", "min_lat_e7", "max_lon_e7", "max_lat_e7"]
    ]
    data = read_pmtiles(archive, bounds)
    for feature in data["features"]:
        geometry = shape(feature["geometry"])
        parts = list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]
        cleaned = []
        for polygon in parts:
            if polygon.geom_type != "Polygon" or polygon.area < 5e-8:
                continue
            holes = [
                ring.coords for ring in polygon.interiors if Polygon(ring).area >= 5e-8
            ]
            simplified = Polygon(polygon.exterior.coords, holes).simplify(
                0.0002, preserve_topology=True
            )
            if not simplified.is_empty:
                cleaned.append(simplified)
        feature["geometry"] = mapping(MultiPolygon(cleaned))
    target = BASE / "data/noah-display.geojson"
    target.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {target.stat().st_size:,} bytes to {target}")


if __name__ == "__main__":
    main()
