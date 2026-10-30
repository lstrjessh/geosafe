import { useEffect, useRef, useState } from "react";
import MapView from "./Map";
import Compare from "./Compare";
import {
  API,
  request,
  type Assessment,
  type Bounds,
  type Job,
  type Observation,
} from "./api";

const initialBounds: Bounds = [124.2, 8.18, 124.28, 8.26];
const layerNames: Record<string, string> = {
  risk_score: "Satellite indicator score",
  hotspots: "Relative hotspots",
  ndvi_change: "NDVI change",
  slope: "Slope (degrees)",
  baseline_ndvi: "Baseline vegetation (NDVI)",
  recent_ndvi: "Recent vegetation (NDVI)",
};

function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Try again.";
}
function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

export default function App() {
  const [tab, setTab] = useState("assessment");
  const [drawing, setDrawing] = useState(false),
    [opacity, setOpacity] = useState(0.5),
    [reset, setReset] = useState(0),
    [compare, setCompare] = useState(false),
    [layersOpen, setLayersOpen] = useState(false);
  const [pointValues, setPointValues] = useState<Record<
      string,
      number | null
    > | null>(null),
    [pointError, setPointError] = useState("");
  const [localMode, setLocalMode] = useState(false),
    [rasters, setRasters] = useState<(File | null)[]>([null, null, null]);
  const [bounds, setBounds] = useState<Bounds>(initialBounds),
    [region, setRegion] = useState(initialBounds.map(String));
  const [archive, setArchive] = useState<{
    bounds: Bounds;
    max_zoom: number;
  } | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [sourceLoading, setSourceLoading] = useState(true),
    [visible, setVisible] = useState(true),
    [regionError, setRegionError] = useState("");
  const [selected, setSelected] = useState<[number, number] | null>(null),
    [coordinate, setCoordinate] = useState(["8.22", "124.24"]);
  const [assessment, setAssessment] = useState<Assessment | null>(null),
    [assessmentError, setAssessmentError] = useState("");
  const [assessing, setAssessing] = useState(false),
    [job, setJob] = useState<Job | null>(null),
    [jobError, setJobError] = useState("");
  const [submitting, setSubmitting] = useState(false),
    [raster, setRaster] = useState("risk_score");
  const [observations, setObservations] = useState<Observation[]>([]),
    [observationError, setObservationError] = useState(""),
    [uploading, setUploading] = useState(false);
  const [dates, setDates] = useState([
    "2020-01-01",
    "2020-03-01",
    "2025-01-01",
    "2025-03-01",
  ]);
  const [weights, setWeights] = useState([0.45, 0.35, 0.2]),
    [cloud, setCloud] = useState(40);
  const [params, setParams] = useState({
    vegetation: 0.2,
    water: 0.1,
    percentile: 90,
  });
  const epoch = useRef(0),
    uploadVersion = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    setSourceLoading(true);
    setArchive(null);
    setSourceError("");
    request<{ landslide_archive: { bounds: Bounds; max_zoom: number } | null }>(
      "/api/config",
      { signal: controller.signal },
    )
      .then((data) => {
        setArchive(data.landslide_archive);
        setSourceLoading(false);
      })
      .catch((error) => {
        if (!isAbort(error)) {
          setSourceError(message(error));
          setSourceLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setAssessing(true);
    setAssessment(null);
    setAssessmentError("");
    request<Assessment>(
      `/api/assessment?lat=${selected[0]}&lon=${selected[1]}`,
      { signal: controller.signal },
    )
      .then((data) => {
        setAssessment(data);
        setAssessing(false);
      })
      .catch((error) => {
        if (!isAbort(error)) {
          setAssessmentError(message(error));
          setAssessing(false);
        }
      });
    return () => controller.abort();
  }, [selected]);

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const id = job.id,
      controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await request<Job>(`/api/analysis/${id}`, {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setJob(next);
        if (["queued", "running"].includes(next.status))
          timer = setTimeout(poll, 2000);
      } catch (error) {
        if (!isAbort(error)) {
          setJobError(message(error));
          setJob(null);
        }
      }
    };
    timer = setTimeout(poll, 1000);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [job?.id, job?.status]);

  useEffect(() => {
    setPointValues(null);
    setPointError("");
    if (!selected || job?.status !== "succeeded") return;
    const controller = new AbortController();
    request<{ values: Record<string, number | null> }>(
      `/api/analysis/${job.id}/point?lat=${selected[0]}&lon=${selected[1]}`,
      { signal: controller.signal },
    )
      .then((data) => setPointValues(data.values))
      .catch((error) => {
        if (!isAbort(error)) setPointError(message(error));
      });
    return () => controller.abort();
  }, [selected, job?.id, job?.status]);

  function select(lat: number, lon: number) {
    setSelected([lat, lon]);
    setCoordinate([lat.toFixed(6), lon.toFixed(6)]);
    setTab("assessment");
  }
  function setArea(values: Bounds) {
    if (
      values.some((value) => !Number.isFinite(value)) ||
      values[0] >= values[2] ||
      values[1] >= values[3] ||
      values[0] < -180 ||
      values[2] > 180 ||
      values[1] < -85 ||
      values[3] > 85
    ) {
      setRegionError("Enter valid west/south and east/north coordinates.");
      return;
    }
    const area =
      (values[2] - values[0]) *
      111.32 *
      Math.cos((((values[1] + values[3]) / 2) * Math.PI) / 180) *
      (values[3] - values[1]) *
      111.32;
    if (area > 144) {
      setRegionError(
        "Select a region smaller than 144 km² for interactive processing.",
      );
      return;
    }
    epoch.current++;
    setBounds(values);
    setRegionError("");
    setJob(null);
    setJobError("");
    setSelected(null);
    setAssessment(null);
    setCompare(false);
    setDrawing(false);
    setRegion(values.map(String));
  }
  function applyRegion(event: React.FormEvent) {
    event.preventDefault();
    setArea(region.map(Number) as Bounds);
  }
  async function startAnalysis(event: React.FormEvent) {
    event.preventDefault();
    setJobError("");
    if (
      !localMode &&
      (dates[0] > dates[1] || dates[2] > dates[3] || dates[1] >= dates[2])
    ) {
      setJobError("Choose non-overlapping periods, with the baseline first.");
      return;
    }
    if (weights.reduce((a, b) => a + b, 0) <= 0) {
      setJobError("Set at least one positive analysis weight.");
      return;
    }
    if (localMode && rasters.some((file) => !file)) {
      setJobError(
        "Choose baseline, recent reflectance, and elevation GeoTIFFs.",
      );
      return;
    }
    setSubmitting(true);
    setJob(null);
    setCompare(false);
    const version = epoch.current;
    try {
      let response: { id: string };
      if (localMode) {
        const data = new FormData();
        ["baseline", "recent", "dem"].forEach((key, i) =>
          data.append(key, rasters[i]!),
        );
        data.append("bounds", JSON.stringify(bounds));
        data.append("weights", JSON.stringify(weights));
        data.append("vegetation_threshold", String(params.vegetation));
        data.append("water_threshold", String(params.water));
        data.append("percentile", String(params.percentile));
        response = await request<{ id: string }>("/api/analysis-upload", {
          method: "POST",
          body: data,
        });
      } else {
        response = await request<{ id: string }>("/api/analysis", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            bounds,
            historical: dates.slice(0, 2),
            recent: dates.slice(2, 4),
            weights,
            cloud,
            vegetation_threshold: params.vegetation,
            water_threshold: params.water,
            percentile: params.percentile,
          }),
        });
      }
      if (version === epoch.current) {
        setJob({
          id: response.id,
          status: "queued",
          message: "Waiting for the analysis worker",
        });
        setRaster("risk_score");
      }
    } catch (error) {
      if (version === epoch.current) setJobError(message(error));
    } finally {
      setSubmitting(false);
    }
  }
  async function upload(file: File | undefined) {
    const version = ++uploadVersion.current;
    setObservationError("");
    setObservations([]);
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      setObservationError("Limit observation CSVs to 2 MB.");
      return;
    }
    setUploading(true);
    const data = new FormData();
    data.append("file", file);
    try {
      const result = await request<{ observations: Observation[] }>(
        "/api/observations",
        { method: "POST", body: data },
      );
      if (version === uploadVersion.current)
        setObservations(result.observations);
    } catch (error) {
      if (version === uploadVersion.current)
        setObservationError(message(error));
    } finally {
      if (version === uploadVersion.current) setUploading(false);
    }
  }
  const busy =
    submitting || (!!job && ["queued", "running"].includes(job.status));
  const archiveOverlaps =
    archive &&
    !(
      bounds[2] < archive.bounds[0] ||
      bounds[0] > archive.bounds[2] ||
      bounds[3] < archive.bounds[1] ||
      bounds[1] > archive.bounds[3]
    );
  const result = job?.status === "succeeded" ? job.result : null;

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/">
          <img src="/icon.svg" width="36" height="36" alt="" />
          <span>
            GeoSafe<small>LANDSLIDE ASSESSMENT</small>
          </span>
        </a>
        <div className="header-meta">
          <span>WORKSPACE</span>
          <span className="status-dot" />
          NOAH / SENTINEL-2 / COPERNICUS
        </div>
        <a
          className="source-link"
          href="https://github.com/lstrjessh/PhilSA-GeoSafe-Landslide-Risk-Mapper"
          target="_blank"
          rel="noreferrer"
        >
          Source ↗
        </a>
      </header>
      <div className="workspace">
        <nav className="navrail" aria-label="Workspace tools">
          {[
            ["assessment", "◎", "Inspect"],
            ["analysis", "◫", "Analyze"],
            ["observations", "⌁", "Sensors"],
            ["sources", "▤", "Sources"],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              aria-pressed={tab === id}
              onClick={() => setTab(id)}
            >
              <span aria-hidden="true">{icon}</span>
              <small>{label}</small>
            </button>
          ))}
        </nav>
        <aside className="sidebar">
          <div className="panel-heading">
            <span className="eyebrow">GEOSPATIAL WORKSPACE</span>
            <h1>
              {tab === "assessment"
                ? "Location inspector"
                : tab === "analysis"
                  ? "Change analysis"
                  : tab === "sources"
                    ? "Source explorer"
                    : "Observations"}
            </h1>
            <p>
              {tab === "assessment"
                ? "Examine mapped exposure and pixel-level indicators."
                : tab === "analysis"
                  ? "Compare periods. Trace the data behind each result."
                  : tab === "sources"
                    ? "Provenance, coverage, and the limits of the data."
                    : "Measured readings from your field sensors."}
            </p>
          </div>
          <div className="panel-scroll">
            <details className="region-settings">
              <summary>
                Analysis region{" "}
                <span>
                  {bounds[1].toFixed(2)}° N, {bounds[0].toFixed(2)}° E
                </span>
              </summary>
              <form onSubmit={applyRegion}>
                <div className="input-grid">
                  {[
                    "West longitude",
                    "South latitude",
                    "East longitude",
                    "North latitude",
                  ].map((label, i) => (
                    <label key={label}>
                      {label}
                      <input
                        type="number"
                        step="any"
                        value={region[i]}
                        required
                        onChange={(event) =>
                          setRegion(
                            region.map((value, j) =>
                              i === j ? event.target.value : value,
                            ),
                          )
                        }
                      />
                    </label>
                  ))}
                </div>
                <button className="secondary" type="submit">
                  Apply region
                </button>
                {regionError && (
                  <p className="error" role="alert">
                    {regionError}
                  </p>
                )}
                <p className="fine">
                  Changing the region clears the displayed satellite result.
                </p>
              </form>
            </details>
            {tab === "assessment" && (
              <section
                id="panel-assessment"
                role="tabpanel"
                aria-labelledby="tab-assessment"
              >
                <h2>Location assessment</h2>
                <p className="muted">
                  Select a point on the map or enter its coordinates.
                </p>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    select(Number(coordinate[0]), Number(coordinate[1]));
                  }}
                >
                  <div className="input-grid">
                    <label>
                      Latitude
                      <input
                        type="number"
                        step="any"
                        min="-85"
                        max="85"
                        required
                        value={coordinate[0]}
                        onChange={(event) =>
                          setCoordinate([event.target.value, coordinate[1]])
                        }
                      />
                    </label>
                    <label>
                      Longitude
                      <input
                        type="number"
                        step="any"
                        min="-180"
                        max="180"
                        required
                        value={coordinate[1]}
                        onChange={(event) =>
                          setCoordinate([coordinate[0], event.target.value])
                        }
                      />
                    </label>
                  </div>
                  <button
                    className="primary"
                    type="submit"
                    disabled={assessing}
                  >
                    {assessing ? "Assessing…" : "Assess location"}
                    <span>→</span>
                  </button>
                </form>
                {assessmentError && (
                  <p className="error" role="alert">
                    {assessmentError}
                  </p>
                )}
                {assessment && (
                  <div
                    className={`assessment-result level-${assessment.level?.toLowerCase() || "unknown"}`}
                    aria-live="polite"
                  >
                    <span className="eyebrow">MAPPED SUSCEPTIBILITY</span>
                    <h3>{assessment.level || "No mapped class"}</h3>
                    <p>
                      {assessment.level
                        ? "Published NOAH susceptibility at this location."
                        : "No class was found. Check source coverage; this does not establish safety."}
                    </p>
                    <small>
                      {assessment.latitude.toFixed(5)},{" "}
                      {assessment.longitude.toFixed(5)}
                    </small>
                  </div>
                )}
                {pointError && (
                  <p className="error" role="alert">
                    {pointError}
                  </p>
                )}
                {pointValues && (
                  <div className="pixel-inspector">
                    <span className="eyebrow">SATELLITE PIXEL</span>
                    {Object.entries(pointValues).map(([name, value]) => (
                      <div key={name}>
                        <span>{layerNames[name] || name}</span>
                        <strong>
                          {value === null ? "No data" : value.toFixed(3)}
                        </strong>
                      </div>
                    ))}
                    <p className="fine">
                      Sampled from the analysis rasters at your selected
                      coordinate.
                    </p>
                  </div>
                )}
                <div className="context-note">
                  <h3>A map, not a live warning.</h3>
                  <p>
                    NOAH classes describe mapped susceptibility. They do not
                    show current landslide activity. Areas without mapped data
                    should not be treated as safe.
                  </p>
                </div>
              </section>
            )}
            {tab === "analysis" && (
              <section
                id="panel-analysis"
                role="tabpanel"
                aria-labelledby="tab-analysis"
              >
                <div className="source-mode">
                  <button
                    aria-pressed={!localMode}
                    onClick={() => setLocalMode(false)}
                  >
                    Public imagery
                  </button>
                  <button
                    aria-pressed={localMode}
                    onClick={() => setLocalMode(true)}
                  >
                    Local GeoTIFFs
                  </button>
                </div>
                <form onSubmit={startAnalysis}>
                  {localMode ? (
                    <div className="raster-inputs">
                      {[
                        "Baseline reflectance",
                        "Recent reflectance",
                        "Elevation (DEM)",
                      ].map((label, i) => (
                        <label key={label}>
                          {label}
                          <input
                            type="file"
                            accept=".tif,.tiff"
                            onChange={(event) =>
                              setRasters(
                                rasters.map((file, j) =>
                                  i === j
                                    ? event.target.files?.[0] || null
                                    : file,
                                ),
                              )
                            }
                          />
                        </label>
                      ))}
                      <p className="fine">
                        Maximum 50 MB each. Reflectance bands: green, red, NIR,
                        in 0–1 units or with scale/offset metadata. Optional
                        fourth band: SCL. Otherwise use cloud-masked data. DEM
                        elevations must be metres.
                      </p>
                    </div>
                  ) : (
                    <>
                      <div className="date-group">
                        <h3>Baseline period</h3>
                        <div className="input-grid">
                          {[0, 1].map((i) => (
                            <label key={i}>
                              {i === 0 ? "From" : "To"}
                              <input
                                type="date"
                                required
                                value={dates[i]}
                                onChange={(event) =>
                                  setDates(
                                    dates.map((value, j) =>
                                      j === i ? event.target.value : value,
                                    ),
                                  )
                                }
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                      <div className="date-group">
                        <h3>Recent period</h3>
                        <div className="input-grid">
                          {[2, 3].map((i) => (
                            <label key={i}>
                              {i === 2 ? "From" : "To"}
                              <input
                                type="date"
                                required
                                value={dates[i]}
                                onChange={(event) =>
                                  setDates(
                                    dates.map((value, j) =>
                                      j === i ? event.target.value : value,
                                    ),
                                  )
                                }
                              />
                            </label>
                          ))}
                        </div>
                      </div>
                    </>
                  )}
                  <details className="parameters">
                    <summary>Analysis parameters</summary>
                    {["Vegetation loss", "NDWI", "Slope"].map((label, i) => (
                      <label className="range" key={label}>
                        {label}
                        <output>{weights[i].toFixed(2)}</output>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step=".05"
                          value={weights[i]}
                          onChange={(event) =>
                            setWeights(
                              weights.map((w, j) =>
                                j === i ? Number(event.target.value) : w,
                              ),
                            )
                          }
                        />
                      </label>
                    ))}
                    <label className="range">
                      Maximum scene cloud cover<output>{cloud}%</output>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={cloud}
                        onChange={(event) =>
                          setCloud(Number(event.target.value))
                        }
                      />
                    </label>
                    <label>
                      Baseline vegetation threshold
                      <input
                        type="number"
                        min="0"
                        max=".8"
                        step=".01"
                        value={params.vegetation}
                        onChange={(event) =>
                          setParams({
                            ...params,
                            vegetation: Number(event.target.value),
                          })
                        }
                      />
                    </label>
                    <label>
                      Water exclusion threshold
                      <input
                        type="number"
                        min="0"
                        max=".6"
                        step=".01"
                        value={params.water}
                        onChange={(event) =>
                          setParams({
                            ...params,
                            water: Number(event.target.value),
                          })
                        }
                      />
                    </label>
                    <label>
                      Hotspot percentile
                      <input
                        type="number"
                        min="75"
                        max="99"
                        value={params.percentile}
                        onChange={(event) =>
                          setParams({
                            ...params,
                            percentile: Number(event.target.value),
                          })
                        }
                      />
                    </label>
                  </details>
                  <button className="primary" type="submit" disabled={busy}>
                    {busy ? "Analysis running…" : "Run analysis"}
                    <span>→</span>
                  </button>
                </form>
                {jobError && (
                  <p className="error" role="alert">
                    {jobError}
                  </p>
                )}
                {job && (
                  <div
                    className={`job-status ${job.status === "failed" ? "error" : ""}`}
                    role="status"
                  >
                    {busy && <span className="spinner" />}
                    {job.message}
                  </div>
                )}
                {result && job && (
                  <div className="analysis-result">
                    <div className="metrics">
                      <div>
                        <strong>
                          {result.metadata.coverage_percent.toFixed(1)}%
                        </strong>
                        <span>Valid coverage</span>
                      </div>
                      <div>
                        <strong>
                          {result.metadata.mean_ndvi_change.toFixed(3)}
                        </strong>
                        <span>NDVI change</span>
                      </div>
                      <div>
                        <strong>
                          {result.metadata.hotspot_area_km2.toFixed(2)}
                        </strong>
                        <span>Hotspots (km²)</span>
                      </div>
                    </div>
                    {result.metadata.coverage_percent < 50 && (
                      <p className="error">
                        Less than half the region has valid observations.
                        Interpret these results within that coverage.
                      </p>
                    )}
                    <button
                      type="button"
                      className="secondary comparison-button"
                      onClick={() => setCompare(true)}
                    >
                      Compare baseline & recent ↔
                    </button>
                    <label>
                      Map layer
                      <select
                        value={raster}
                        onChange={(event) => setRaster(event.target.value)}
                      >
                        <option value="">Hide satellite layer</option>
                        {Object.entries(layerNames).map(([id, label]) => (
                          <option key={id} value={id}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <a
                      className="download-link"
                      href={`${API}/api/analysis/${job.id}/files/analysis.zip`}
                    >
                      Download GeoTIFF bundle ↓
                    </a>
                    <a
                      className="download-link"
                      href={`${API}/api/analysis/${job.id}/files/metadata.json`}
                    >
                      View source metadata ↗
                    </a>
                  </div>
                )}
                <p className="fine">
                  Uses up to four low-cloud Sentinel-2 scenes per period and
                  Copernicus DEM, at 30 m. Processing can take several minutes.
                  Results expire after an hour or a server restart.
                </p>
                <p className="fine">
                  Scores are relative indicators, not landslide probabilities or
                  NOAH classes. NDWI is not a direct measurement of soil
                  moisture.
                </p>
              </section>
            )}
            {tab === "observations" && (
              <section
                id="panel-observations"
                role="tabpanel"
                aria-labelledby="tab-observations"
              >
                <h2>Sensor observations</h2>
                <p className="muted">
                  Import measured readings. No synthetic sensors or hazard
                  predictions are added.
                </p>
                <label className="file-upload">
                  Upload observation CSV
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    onChange={(event) => void upload(event.target.files?.[0])}
                  />
                </label>
                {uploading && <p role="status">Reading observations…</p>}
                {observationError && (
                  <p className="error" role="alert">
                    {observationError}
                  </p>
                )}
                {observations.length > 0 && (
                  <>
                    <div className="metrics">
                      <div>
                        <strong>
                          {new Set(observations.map((row) => row.node_id)).size}
                        </strong>
                        <span>Nodes</span>
                      </div>
                      <div>
                        <strong>{observations.length}</strong>
                        <span>Observations</span>
                      </div>
                    </div>
                    <button
                      className="secondary"
                      onClick={() => {
                        uploadVersion.current++;
                        setObservations([]);
                      }}
                    >
                      Clear observations
                    </button>
                    <div className="observation-list">
                      {observations
                        .slice(-8)
                        .reverse()
                        .map((row, i) => (
                          <div key={i}>
                            <strong>{row.node_id}</strong>
                            <time>{row.timestamp}</time>
                            <p>
                              {Object.entries(row)
                                .filter(
                                  ([key]) =>
                                    ![
                                      "node_id",
                                      "latitude",
                                      "longitude",
                                      "timestamp",
                                    ].includes(key),
                                )
                                .map(([key, value]) => `${key}: ${value}`)
                                .join(" · ")}
                            </p>
                          </div>
                        ))}
                    </div>
                  </>
                )}
                <details className="context-note">
                  <summary>CSV format</summary>
                  <a
                    className="download-link"
                    href="/observation-template.csv"
                    download
                  >
                    Download CSV template ↓
                  </a>
                  <p>
                    Required: node_id, latitude, longitude, timestamp. Include a
                    sensor value such as soil_moisture, tilt_x, temperature, or
                    humidity. Timestamps need a timezone. Maximum file size: 2
                    MB.
                  </p>
                  <p>
                    Soil moisture and humidity use percent; temperature uses °C,
                    tilt uses degrees, and pressure uses hPa. Imported readings
                    are not automatically validated as hazard evidence.
                  </p>
                </details>
              </section>
            )}
            {tab === "sources" && (
              <section id="panel-sources">
                <h2>Data provenance</h2>
                <div className="source-card">
                  <span className="eyebrow">PUBLISHED SUSCEPTIBILITY</span>
                  <h3>UP RI NOAH</h3>
                  <p>
                    Landslide polygons for Lanao del Norte and nearby areas. LH
                    = 1, 2, 3. Display tiles are generalized; point queries use
                    native archive detail.
                  </p>
                  <p>
                    {archive
                      ? `Original PMTiles archive · maximum zoom ${archive.max_zoom}`
                      : "Archive unavailable"}
                  </p>
                </div>
                <div className="source-card">
                  <span className="eyebrow">SATELLITE OBSERVATIONS</span>
                  <h3>Sentinel-2 L2A</h3>
                  <p>
                    Surface reflectance from Earth Search COGs. SCL classes 4,
                    5, and 6 are retained. Cloudy and missing pixels stay
                    masked.
                  </p>
                  <p>
                    Up to four low-cloud scenes per period. Repeated processing
                    versions of the same tile/day are deduplicated.
                  </p>
                </div>
                <div className="source-card">
                  <span className="eyebrow">TERRAIN</span>
                  <h3>Copernicus DEM GLO-30</h3>
                  <p>
                    Slope is calculated locally on a 30 m projected grid. It
                    represents surface topography, not subsurface stability.
                  </p>
                </div>
                {result && (
                  <details className="source-metadata" open>
                    <summary>Current analysis metadata</summary>
                    <pre>{JSON.stringify(result.metadata, null, 2)}</pre>
                    <a
                      className="download-link"
                      href={`${API}/api/analysis/${job!.id}/files/metadata.json`}
                    >
                      Download provenance JSON ↓
                    </a>
                  </details>
                )}
              </section>
            )}
          </div>
          <div className="panel-footer">
            <a href="https://noah.upd.edu.ph/" target="_blank" rel="noreferrer">
              UP RI NOAH ↗
            </a>
            <a
              href="https://element84.com/earth-search/"
              target="_blank"
              rel="noreferrer"
            >
              Earth Search ↗
            </a>
          </div>
        </aside>
        <main className="map-column">
          <div className="map-toolbar">
            <div>
              <span className="status-dot" />
              <span>
                {sourceLoading
                  ? "Loading susceptibility…"
                  : sourceError
                    ? "Source unavailable"
                    : archiveOverlaps
                      ? "Susceptibility archive ready"
                      : "Outside archive bounds"}
              </span>
            </div>
            <div className="map-actions">
              <button
                className={layersOpen ? "active" : ""}
                onClick={() => setLayersOpen(!layersOpen)}
              >
                Layers
              </button>
              <button
                className={drawing ? "active" : ""}
                onClick={() => setDrawing(!drawing)}
              >
                {drawing ? "Cancel selection" : "Select region"}
              </button>
              <button onClick={() => setReset(reset + 1)}>Fit region</button>
              {result && (
                <button onClick={() => setCompare(!compare)}>Compare ↔</button>
              )}
            </div>
          </div>
          {sourceError && (
            <p className="source-error" role="alert">
              {sourceError}
            </p>
          )}
          <MapView
            bounds={bounds}
            selected={selected}
            onSelect={select}
            visible={visible}
            job={job}
            raster={raster}
            observations={observations}
            drawing={drawing}
            onDraw={setArea}
            opacity={opacity}
            reset={reset}
          />
          {layersOpen && (
            <div className="floating-layers">
              <span className="eyebrow">MAP LAYERS</span>
              <label className="layer-toggle">
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={(event) => setVisible(event.target.checked)}
                />
                NOAH susceptibility
              </label>
              {visible && (
                <label className="opacity-label">
                  Opacity
                  <input
                    aria-label="Susceptibility opacity"
                    type="range"
                    min="0"
                    max="1"
                    step=".05"
                    value={opacity}
                    onChange={(event) => setOpacity(Number(event.target.value))}
                  />
                </label>
              )}
              {result && (
                <label>
                  Analysis layer
                  <select
                    value={raster}
                    onChange={(event) => setRaster(event.target.value)}
                  >
                    <option value="">Hidden</option>
                    {Object.entries(layerNames).map(([id, label]) => (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          )}
          {compare && job && (
            <Compare job={job} onClose={() => setCompare(false)} />
          )}
          {result && (
            <div className="result-strip">
              <span className="eyebrow">ANALYSIS RESULT</span>
              <div>
                <strong>{result.metadata.coverage_percent.toFixed(1)}%</strong>
                <span>valid coverage</span>
              </div>
              <div>
                <strong>{result.metadata.mean_ndvi_change.toFixed(3)}</strong>
                <span>NDVI change</span>
              </div>
              <div>
                <strong>
                  {result.metadata.hotspot_area_km2.toFixed(2)} km²
                </strong>
                <span>relative hotspots</span>
              </div>
              <button onClick={() => setCompare(true)}>
                Compare periods ↔
              </button>
            </div>
          )}
          <div className="map-footer">
            <span className="legend">
              <i className="low" />
              Low
              <i className="medium" />
              Medium
              <i className="high" />
              High <span>mapped susceptibility</span>
            </span>
            <span>Research assessment · Not an official advisory</span>
          </div>
        </main>
      </div>
    </div>
  );
}
