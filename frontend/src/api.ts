import type * as GeoJSON from "geojson";
export const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(API + path, options);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : body.detail?.map((item: { msg: string }) => item.msg).join("; ") ||
            message;
    } catch {
      /* retain HTTP status */
    }
    throw new Error(message);
  }
  return response.json();
}
export type Bounds = [number, number, number, number];
export type Layer = { id: string; coordinates: [number, number][] };
export type Result = {
  metadata: {
    coverage_percent: number;
    mean_ndvi_change: number;
    hotspot_area_km2: number;
    [key: string]: unknown;
  };
  layers: Layer[];
  samples: GeoJSON.FeatureCollection;
};
export type Job = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  message: string;
  result?: Result;
};
export type Assessment = {
  latitude: number;
  longitude: number;
  level: string | null;
  interpretation: string;
};
export type Observation = {
  node_id: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  [key: string]: string | number;
};
