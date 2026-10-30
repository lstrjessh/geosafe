"""Import measured sensor observations. No synthetic nodes or inferred readings."""

import csv
import math
from datetime import datetime, timedelta, timezone
from io import StringIO

SENSORS = [
    "soil_moisture",
    "tilt_x",
    "tilt_y",
    "tilt_z",
    "vibration",
    "temperature",
    "humidity",
    "pressure",
]


def read_observations(content):
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Sensor uploads must be smaller than 2 MB.")
    reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
    required = {"node_id", "latitude", "longitude", "timestamp"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError(
            "CSV requires node_id, latitude, longitude, timestamp, and at least one sensor field."
        )
    observations = []
    seen = set()
    for line, row in enumerate(reader, 2):
        if line > 10001:
            raise ValueError("Limit sensor uploads to 10,000 observations.")
        try:
            node = row["node_id"].strip()
            lat, lon = float(row["latitude"]), float(row["longitude"])
            time = datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00"))
            if (
                not node
                or len(node) > 100
                or not (
                    math.isfinite(lat)
                    and math.isfinite(lon)
                    and -90 <= lat <= 90
                    and -180 <= lon <= 180
                )
            ):
                raise ValueError("invalid node ID or coordinates")
            if time.tzinfo is None:
                raise ValueError("timestamps require a timezone, such as +08:00 or Z")
            time = time.astimezone(timezone.utc)
            if time > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("timestamp is in the future")
            values = {}
            for field in SENSORS:
                if row.get(field, "").strip():
                    value = float(row[field])
                    if not math.isfinite(value):
                        raise ValueError("sensor values must be finite")
                    if field in ["soil_moisture", "humidity"] and not 0 <= value <= 100:
                        raise ValueError(f"{field} must be between 0 and 100 percent")
                    values[field] = value
            if not values:
                raise ValueError("include at least one measured sensor value")
            key = (node, time)
            if key in seen:
                raise ValueError("duplicate node and timestamp")
            seen.add(key)
            observations.append(
                {
                    "node_id": node,
                    "latitude": lat,
                    "longitude": lon,
                    "timestamp": time.isoformat(),
                    **values,
                }
            )
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError(f"Sensor CSV row {line}: {error}") from error
    if not observations:
        raise ValueError("Sensor CSV has no observations.")
    return sorted(observations, key=lambda r: r["timestamp"])
