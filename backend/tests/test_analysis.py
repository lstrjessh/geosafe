import json
from zipfile import ZipFile

import numpy as np
import pytest
from geosafe.analysis import calculate, samples_for, weights_normalized
from geosafe.exports import geotiff, preview, write_results
from geosafe.satellite import grid_for, index, slope_from_dem
from geosafe.uploads import run_uploaded
from rasterio.io import MemoryFile
from rasterio.transform import from_origin


def grid():
    return {
        "crs": "EPSG:32651",
        "transform": from_origin(630000, 910000, 30, 30),
        "width": 6,
        "height": 6,
        "resolution": 30,
    }


def data():
    old = np.full((6, 6), 0.6, dtype="float32")
    current = old.copy()
    current[:3, :3] = 0.05
    water = np.full((6, 6), -0.1, dtype="float32")
    slope = np.full((6, 6), 12, dtype="float32")
    images, stats = calculate((current, water), (old, water), slope, grid(), [1, 0, 0])
    return images, stats


def test_weights_and_limits():
    assert weights_normalized([1, 2, 1]) == [0.25, 0.5, 0.25]
    for weights in [[0, 0, 0], [1, -1, 1], [float("nan"), 1, 1]]:
        with pytest.raises(ValueError):
            weights_normalized(weights)
    with pytest.raises(ValueError):
        grid_for([124, 8, 126, 10])
    with pytest.raises(ValueError):
        grid_for([124, 8, 124, 8])


def test_vegetation_loss_is_retained():
    images, stats = data()
    assert stats["valid_pixels"] == 36
    assert images["risk_score"][0, 0] == pytest.approx(1)
    assert images["ndvi_change"][0, 0] == pytest.approx(-0.55)
    assert stats["hotspot_percent"] == 25


def test_zero_scores_do_not_make_hotspots():
    a = np.full((6, 6), 0.6)
    w = np.full((6, 6), -0.1)
    images, stats = calculate((a, w), (a, w), np.zeros((6, 6)), grid(), [1, 0, 0])
    assert stats["hotspot_area_km2"] == 0
    assert np.nansum(images["hotspots"]) == 0


def test_water_and_missing_data_are_not_low_risk():
    a = np.full((6, 6), 0.6)
    w = np.full((6, 6), 0.5)
    with pytest.raises(ValueError, match="No valid"):
        calculate((a, w), (a, w), a, grid(), [1, 0, 0])
    ndvi = index(np.zeros((2, 2)), np.zeros((2, 2)))
    assert np.isnan(ndvi).all()


def test_slope_uses_metric_spacing():
    elevation = np.tile(np.arange(6) * 30, (6, 1))
    assert np.allclose(slope_from_dem(elevation, 30), 45)


def test_geotiff_and_png_have_real_data():
    images, _ = data()
    content = geotiff(images["risk_score"], grid())
    with MemoryFile(content) as memory:
        with memory.open() as raster:
            assert raster.crs.to_epsg() == 32651
            assert raster.read(1)[0, 0] == pytest.approx(1)
            assert raster.transform.a == 30
    png, coordinates = preview(images["risk_score"], grid(), "risk_score")
    assert png.startswith(b"\x89PNG")
    assert len(coordinates) == 4


def test_bundle_scoped_to_current_result(tmp_path):
    images, stats = data()
    g = grid()
    samples = samples_for(images, g)
    result = {"images": images, "grid": g, "samples": samples, "metadata": stats}
    output = write_results(result, tmp_path)
    assert len(samples["features"]) == 36
    assert len(output["layers"]) == 6
    with ZipFile(tmp_path / "analysis.zip") as archive:
        assert "metadata.json" in archive.namelist()
        assert "baseline_ndvi.tif" in archive.namelist()
        meta = json.loads(archive.read("metadata.json"))
        assert "risk_score.tif" in meta["sha256"]
        assert len(meta["sha256"]["risk_score.tif"]) == 64
        assert len(archive.namelist()) == 8


def test_upload_pipeline(tmp_path):
    from rasterio.warp import transform_bounds

    g = grid()
    paths = []
    for name, values in [
        ("old", [0.1, 0.1, 0.6]),
        ("new", [0.1, 0.2, 0.3]),
        ("dem", [100]),
    ]:
        path = tmp_path / (name + ".tif")
        paths.append(path)
        import rasterio

        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            count=len(values),
            height=6,
            width=6,
            dtype="float32",
            crs=g["crs"],
            transform=g["transform"],
            nodata=-9999,
        ) as raster:
            for band, value in enumerate(values, 1):
                raster.write(np.full((6, 6), value, dtype="float32"), band)
    bounds = transform_bounds(g["crs"], "EPSG:4326", 630000, 909820, 630180, 910000)
    result = run_uploaded(list(bounds), paths, [1, 0, 0])
    assert result["metadata"]["mean_ndvi_change"] < 0
    assert len(result["metadata"]["source_sha256"]) == 3


def test_coverage_uses_roi_domain():
    g = grid()
    g["domain_mask"] = np.zeros((6, 6), dtype=bool)
    g["domain_mask"][:3, :3] = True
    a = np.full((6, 6), 0.6)
    w = np.full((6, 6), -0.1)
    images, stats = calculate((a, w), (a, w), np.zeros((6, 6)), g, [1, 0, 0])
    assert stats["valid_pixels"] == 9
    assert stats["coverage_percent"] == 100
    assert np.isnan(images["baseline_ndvi"][5, 5])
