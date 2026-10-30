import { useState } from "react";
import { API, type Job } from "./api";
export default function Compare({
  job,
  onClose,
}: {
  job: Job;
  onClose: () => void;
}) {
  const [split, setSplit] = useState(50);
  return (
    <section
      className="compare-window"
      aria-label="Compare baseline and recent vegetation"
    >
      <header>
        <div>
          <span className="eyebrow">TEMPORAL COMPARISON</span>
          <h2>Vegetation, before and after.</h2>
        </div>
        <button
          className="icon-button"
          aria-label="Close comparison"
          onClick={onClose}
        >
          ×
        </button>
      </header>
      <div className="compare-images">
        <img
          src={`${API}/api/analysis/${job.id}/files/baseline_ndvi.png`}
          alt="Baseline vegetation index"
        />
        <img
          className="recent-image"
          style={{ clipPath: `inset(0 0 0 ${split}%)` }}
          src={`${API}/api/analysis/${job.id}/files/recent_ndvi.png`}
          alt="Recent vegetation index"
        />
        <div className="compare-divider" style={{ left: `${split}%` }}>
          <span>↔</span>
        </div>
        <span className="compare-label baseline">BASELINE NDVI</span>
        <span className="compare-label recent">RECENT NDVI</span>
      </div>
      <label className="compare-range">
        Reveal baseline / recent
        <input
          aria-label="Comparison split"
          type="range"
          min="0"
          max="100"
          value={split}
          onChange={(event) => setSplit(Number(event.target.value))}
        />
      </label>
      <p className="fine">
        Same region and grid. NDVI ranges from −1 to 1, with higher values in
        green. Transparent pixels have no valid observation.
      </p>
    </section>
  );
}
