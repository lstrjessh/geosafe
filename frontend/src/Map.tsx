import type * as GeoJSON from "geojson";
import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
maplibregl.setWorkerUrl(mapWorkerUrl);
import { type GeoJSONSource, type Map as MapInstance } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { API, type Bounds, type Job, type Observation } from "./api";

type Props = {
  bounds: Bounds;
  polygons: GeoJSON.FeatureCollection | null;
  selected: [number, number] | null;
  onSelect: (lat: number, lon: number) => void;
  visible: boolean;
  job: Job | null;
  raster: string;
  observations: Observation[];
  drawing: boolean;
  onDraw: (bounds: Bounds) => void;
  opacity: number;
  reset: number;
};
const empty: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

export default function MapView({
  bounds,
  polygons,
  selected,
  onSelect,
  visible,
  job,
  raster,
  observations,
  drawing,
  onDraw,
  opacity,
  reset,
}: Props) {
  const container = useRef<HTMLDivElement>(null),
    map = useRef<MapInstance | null>(null),
    select = useRef(onSelect);
  const draw = useRef(drawing),
    drawCallback = useRef(onDraw),
    corner = useRef<[number, number] | null>(null);
  draw.current = drawing;
  drawCallback.current = onDraw;
  const [ready, setReady] = useState(false),
    [error, setError] = useState("");
  select.current = onSelect;
  useEffect(() => {
    if (!container.current) return;
    const instance = new maplibregl.Map({
      container: container.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [124.24, 8.22],
      zoom: 11,
      attributionControl: false,
    });
    map.current = instance;
    instance.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );
    instance.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution:
          'Landslide susceptibility: <a href="https://noah.upd.edu.ph/">UP RI NOAH</a>',
      }),
      "bottom-right",
    );
    instance.on("load", () => {
      instance.addSource("noah", { type: "geojson", data: empty });
      instance.addLayer({
        id: "noah-fill",
        type: "fill",
        source: "noah",
        paint: {
          "fill-color": [
            "match",
            ["get", "LH"],
            1,
            "#FED7AA",
            2,
            "#C2410C",
            3,
            "#7C2D12",
            "transparent",
          ],
          "fill-opacity": 0.5,
        },
      });
      instance.addLayer({
        id: "noah-line",
        type: "line",
        source: "noah",
        paint: {
          "line-color": "#8e5738",
          "line-width": 0.5,
          "line-opacity": 0.3,
        },
      });
      instance.addSource("region", { type: "geojson", data: empty });
      instance.addLayer({
        id: "region-line",
        type: "line",
        source: "region",
        paint: {
          "line-color": "#285b4d",
          "line-width": 1.5,
          "line-dasharray": [3, 3],
        },
      });
      instance.addSource("drawing", { type: "geojson", data: empty });
      instance.addLayer({
        id: "drawing-area",
        type: "fill",
        source: "drawing",
        paint: { "fill-color": "#7baf67", "fill-opacity": 0.2 },
      });
      instance.addSource("observations", { type: "geojson", data: empty });
      instance.addLayer({
        id: "observations",
        type: "circle",
        source: "observations",
        paint: {
          "circle-radius": 6,
          "circle-color": "#347ca6",
          "circle-stroke-color": "white",
          "circle-stroke-width": 2,
        },
      });
      setReady(true);
      setError("");
    });
    instance.on("error", (event) => {
      if (!instance.isStyleLoaded()) setError(event.error.message);
    });
    instance.on("click", (event) => {
      if (!draw.current) {
        select.current(event.lngLat.lat, event.lngLat.lng);
        return;
      }
      const point: [number, number] = [event.lngLat.lng, event.lngLat.lat];
      if (!corner.current) {
        corner.current = point;
        return;
      }
      const [x, y] = corner.current;
      corner.current = null;
      drawCallback.current([
        Math.min(x, point[0]),
        Math.min(y, point[1]),
        Math.max(x, point[0]),
        Math.max(y, point[1]),
      ]);
    });
    instance.on("mousemove", (event) => {
      if (!draw.current || !corner.current || !instance.getSource("drawing"))
        return;
      const [x, y] = corner.current;
      const { lng, lat } = event.lngLat;
      (instance.getSource("drawing") as GeoJSONSource).setData({
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [x, y],
              [lng, y],
              [lng, lat],
              [x, lat],
              [x, y],
            ],
          ],
        },
      });
    });
    return () => {
      setReady(false);
      instance.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    const [w, s, e, n] = bounds;
    (instance.getSource("region") as GeoJSONSource).setData({
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [w, s],
            [e, s],
            [e, n],
            [w, n],
            [w, s],
          ],
        ],
      },
      properties: {},
    });
    instance.fitBounds(
      [
        [w, s],
        [e, n],
      ],
      { padding: 45, duration: 400 },
    );
  }, [ready, bounds, reset]);
  useEffect(() => {
    if (!ready || !map.current) return;
    map.current.getCanvas().style.cursor = drawing ? "crosshair" : "";
    if (!drawing) {
      corner.current = null;
      (map.current.getSource("drawing") as GeoJSONSource).setData(empty);
    }
  }, [ready, drawing]);
  useEffect(() => {
    if (ready && map.current)
      map.current.setPaintProperty("noah-fill", "fill-opacity", opacity);
  }, [ready, opacity]);
  useEffect(() => {
    if (ready && map.current)
      (map.current.getSource("noah") as GeoJSONSource).setData(
        polygons || empty,
      );
  }, [ready, polygons]);
  useEffect(() => {
    if (ready && map.current) {
      map.current.setLayoutProperty(
        "noah-fill",
        "visibility",
        visible ? "visible" : "none",
      );
      map.current.setLayoutProperty(
        "noah-line",
        "visibility",
        visible ? "visible" : "none",
      );
    }
  }, [ready, visible]);
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance || !selected) return;
    const marker = new maplibregl.Marker({ color: "#244e42" })
      .setLngLat([selected[1], selected[0]])
      .addTo(instance);
    return () => {
      marker.remove();
    };
  }, [ready, selected]);
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    if (instance.getLayer("analysis-raster"))
      instance.removeLayer("analysis-raster");
    if (instance.getSource("analysis")) instance.removeSource("analysis");
    const layer =
      job?.status === "succeeded"
        ? job.result?.layers.find((layer) => layer.id === raster)
        : null;
    if (layer && job) {
      instance.addSource("analysis", {
        type: "image",
        url: `${API}/api/analysis/${job.id}/files/${layer.id}.png`,
        coordinates: layer.coordinates as [
          [number, number],
          [number, number],
          [number, number],
          [number, number],
        ],
      });
      instance.addLayer(
        {
          id: "analysis-raster",
          type: "raster",
          source: "analysis",
          paint: { "raster-opacity": 0.85, "raster-fade-duration": 0 },
        },
        "region-line",
      );
    }
  }, [ready, job, raster]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const latest = new window.Map<string, Observation>();
    observations.forEach((row) => latest.set(row.node_id, row));
    (map.current.getSource("observations") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: [...latest.values()].map((row) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [row.longitude, row.latitude] },
        properties: { node_id: row.node_id },
      })),
    });
  }, [ready, observations]);
  return (
    <div className="map-shell" data-ready={ready}>
      <div
        className="map-canvas"
        ref={container}
        aria-label="Interactive landslide assessment map"
      />
      {error && (
        <div className="map-error" role="alert">
          Map could not load: {error}. Coordinate assessment remains available
          in the panel.
        </div>
      )}
      <div className="map-hint">
        {drawing
          ? "Select two opposite corners of your analysis region"
          : "Click the map to inspect this location"}
      </div>
    </div>
  );
}
