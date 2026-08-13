/*
  api.js

  Thin wrapper around the EagleWatch AI backend (FastAPI).
  Every function returns already-parsed JSON, or throws on non-2xx
  responses so callers can catch/log errors.
*/

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(`${options.method || "GET"} ${path} failed (${res.status}): ${detail}`);
  }
  return res.json();
}

export const api = {
  getIncidents: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/api/incidents${qs ? `?${qs}` : ""}`);
  },
  getIncident: (id) => request(`/api/incidents/${id}`),
  getStats: () => request("/api/incidents/stats"),
  getMapData: () => request("/api/incidents/map"),
  getAnalytics: () => request("/api/analytics"),

  createDemoDetection: (scenario) =>
    request("/api/demo/detection", {
      method: "POST",
      body: JSON.stringify({ scenario }),
    }),

  // Real AI pipeline (YOLO + ByteTrack). Safe to call even when the
  // backend is running in AI_MODE=demo - getAiStatus just reports
  // running:false and the UI falls back to the scenario runner.
  // video_source is passed through so the AI worker always processes
  // the exact same file the Monitoring panel is showing (see
  // getVideoUrl below / App.jsx toggleMonitoring()).
  getAiStatus: () => request("/api/ai/status"),
  getAiDetections: () => request("/api/ai/detections"),
  startAi: ({ videoSource, cameraId } = {}) => {
    const qs = new URLSearchParams();
    if (videoSource) qs.set("video_source", videoSource);
    if (cameraId) qs.set("camera_id", cameraId);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request(`/api/ai/start${suffix}`, { method: "POST" });
  },
  stopAi: () => request("/api/ai/stop", { method: "POST" }),

  verifyIncident: (id) => request(`/api/incidents/${id}/verify`, { method: "POST" }),
  alertIncident: (id) => request(`/api/incidents/${id}/alert`, { method: "POST" }),
  respondIncident: (id) => request(`/api/incidents/${id}/respond`, { method: "POST" }),
  resolveIncident: (id) => request(`/api/incidents/${id}/resolve`, { method: "POST" }),
};

// Converts a backend incident object into the shape the existing
// EagleWatch UI code already expects (see EagleWatch_AI_Demo.jsx).
// Note: `severity` is intentionally mapped from the backend's
// `display_severity`, which becomes "resolved" once an incident's
// status reaches "Resolved" - this preserves the frontend's original
// badge-coloring convention without the backend ever losing track of
// the incident's real severity level.
export function mapIncident(inc) {
  return {
    id: inc.id,
    category: inc.category,
    label: inc.label,
    sub: inc.sub,
    location: inc.location,
    cam: inc.camera_id,
    confidence: inc.confidence,
    severity: inc.display_severity,
    status: inc.status,
    time: new Date(inc.time),
    x: inc.x,
    y: inc.y,
  };
}

export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Builds a URL to a sample CCTV/demo video served by the backend's
// static file mount (backend/main.py -> /sample_video). Used by the
// Monitoring tab to play a real video behind the AI overlays instead
// of the old black placeholder panel.
export function getVideoUrl(filename) {
  if (!filename) return null;
  return `${BASE_URL}/sample_video/${encodeURIComponent(filename)}`;
}

// Path (relative to the backend process's working directory) that the
// real AI worker should read the SAME file from - passed to
// api.startAi({ videoSource }) so the visible <video> and the YOLO
// pipeline are always looking at identical footage (see spec: "The AI
// and visible video must correspond to the same source").
export function getSampleVideoPath(filename) {
  if (!filename) return null;
  return `sample_video/${filename}`;
}

// URL of the live, AI-annotated MJPEG stream (GET /api/ai/stream).
// Each frame pushed down this stream IS a frame the AI worker just
// finished processing - so an <img> pointed at this URL plays back at
// exactly the AI's real processing rate, not the source video's native
// frame rate. Used as the Monitoring feed while real AI monitoring is
// running (only valid once the worker is actually running).
export function getAiStreamUrl() {
  return `${BASE_URL}/api/ai/stream`;
}
