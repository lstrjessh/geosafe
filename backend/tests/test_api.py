import pytest
from fastapi.testclient import TestClient
from geosafe.landslide import normalize_geojson, query_geojson
from geosafe.main import app
from geosafe.observations import read_observations

client = TestClient(app)


def test_health_and_missing_job():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/analysis/missing").status_code == 404
    assert client.get("/api/analysis/missing/files/analysis.zip").status_code == 404


def test_invalid_analysis_is_rejected_before_work():
    payload = {
        "bounds": [124.22, 8.2, 124.23, 8.21],
        "recent": ["2025-01-01", "2025-03-01"],
        "historical": ["2020-01-01", "2020-03-01"],
        "weights": [0, 0, 0],
    }
    assert client.post("/api/analysis", json=payload).status_code == 422
    payload["weights"] = [1, 1, 1]
    payload["historical"] = payload["recent"]
    assert client.post("/api/analysis", json=payload).status_code == 422
    assert client.get("/api/susceptibility?bounds=0,0,20,20").status_code == 422
    assert client.get("/api/assessment?lat=999&lon=124").status_code == 422


def test_sensor_rows_are_measured_and_timestamped():
    content = b"node_id,latitude,longitude,timestamp,soil_moisture\nA,8.2,124.2,2025-01-01T08:00:00+08:00,42\n"
    rows = read_observations(content)
    assert rows[0]["soil_moisture"] == 42
    assert rows[0]["timestamp"] == "2025-01-01T00:00:00+00:00"
    response = client.post(
        "/api/observations", files={"file": ("readings.csv", content, "text/csv")}
    )
    assert response.status_code == 200
    assert len(response.json()["observations"]) == 1
    with pytest.raises(ValueError):
        read_observations(content.replace(b"42", b"nan"))
    with pytest.raises(ValueError):
        read_observations(content.replace(b"+08:00", b""))
    assert (
        client.post(
            "/api/observations", files={"file": ("bad.csv", b"invalid", "text/csv")}
        ).status_code
        == 422
    )


def test_susceptibility_boundary_and_absence():
    data = normalize_geojson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"LH": 3},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[124, 8], [125, 8], [125, 9], [124, 9], [124, 8]]
                        ],
                    },
                }
            ],
        }
    )
    assert query_geojson(data, 8, 124) == "High"
    assert query_geojson(data, 10, 124) is None
    data["features"][0]["properties"]["LH"] = 4
    with pytest.raises(ValueError):
        normalize_geojson(data)


def test_native_archive_and_no_coverage():
    response = client.get("/api/assessment?lat=8.22&lon=124.24")
    assert response.status_code == 200
    assert response.json()["level"] in [None, "Low", "Medium", "High"]
    assert client.get("/api/assessment?lat=0&lon=0").json()["level"] is None


def test_bad_raster_upload_is_rejected():
    files = {
        key: (key + ".tif", b"", "image/tiff") for key in ["baseline", "recent", "dem"]
    }
    response = client.post(
        "/api/analysis-upload", files=files, data={"bounds": "[124.22,8.2,124.23,8.21]"}
    )
    assert response.status_code == 422


def test_generalized_display_polygons_are_available():
    response = client.get("/api/susceptibility?bounds=124.2,8.18,124.28,8.26")
    assert response.status_code == 200
    data = response.json()
    assert data["features"]
    from shapely.geometry import shape

    assert all(shape(feature["geometry"]).is_valid for feature in data["features"])
    assert len(response.content) < 1_000_000
