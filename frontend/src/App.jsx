import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  LayoutGrid, Video, AlertTriangle, MapPin, BarChart3, ShieldAlert, Car,
  Radio, Clock, CheckCircle2, Siren, Activity, X, Play, Square
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  AreaChart, Area, Cell
} from "recharts";
import { api, mapIncident, sleep, getVideoUrl, getSampleVideoPath, getAiStreamUrl } from "./api.js";

/* ---------------------------------------------------------------
   DATA
--------------------------------------------------------------- */

const STAGES = ["Detected", "Verified", "Alerted", "Responding"];

// Mirrors backend/services/incident_service.py SCENARIOS - kept here too
// so the scenario picker UI can render without a network round trip.
const SCENARIOS = [
  {
    id: "collision",
    category: "accident",
    label: "Vehicle Collision",
    sub: "Two-vehicle junction impact",
    location: "Anna Salai & Mount Rd Jn",
    cam: "CAM-04",
    confidence: 94,
    severity: "critical",
    video: "car_accident.mp4",
  },
  {
    id: "twowheeler",
    category: "accident",
    label: "Two-Wheeler Accident",
    sub: "Single-vehicle loss of control",
    location: "ECR Coastal Road, KM 12",
    cam: "CAM-11",
    confidence: 88,
    severity: "high",
    video: "two_wheeler_accident.mp4",
  },
  {
    id: "distress",
    category: "safety",
    label: "Women Safety Incident",
    sub: "Potential distress, isolated individual",
    location: "T Nagar Bus Terminus",
    cam: "CAM-07",
    confidence: 91,
    severity: "critical",
    video: "women_safety.mp4",
  },
  {
    id: "normal",
    category: "normal",
    label: "Normal Traffic",
    sub: "Routine vehicles & pedestrians, no incident expected",
    location: "Anna Salai & Mount Road",
    cam: "CAM-01",
    confidence: null,
    severity: null,
    video: "normal.mp4",
  },
];

// Incident data now comes from the EagleWatch backend (GET /api/incidents)
// instead of a hardcoded local array - see the initial-load useEffect below.

function timeAgo(d) {
  const m = Math.floor((Date.now() - d.getTime()) / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}
function clockStr(d) {
  return d.toLocaleTimeString("en-IN", { hour12: false });
}

// Maps a raw incident label (from event_analyzer.py) to the short,
// shouty phrase the Monitoring HUD shows - matches the demo's expected
// results ("ACCIDENT DETECTED", "TWO-WHEELER ACCIDENT DETECTED",
// "POTENTIAL DISTRESS / WOMEN SAFETY INCIDENT") without renaming the
// underlying incident records themselves.
function friendlyDetectionLabel(label) {
  if (!label) return null;
  if (/collision/i.test(label)) return "ACCIDENT DETECTED";
  if (/two-wheeler/i.test(label)) return "TWO-WHEELER ACCIDENT DETECTED";
  if (/distress|pursuit|suspicious|safety/i.test(label)) return "POTENTIAL DISTRESS / WOMEN SAFETY INCIDENT";
  return label.toUpperCase();
}

const SEV_COLOR = {
  critical: "var(--red)",
  high: "var(--amber)",
  medium: "var(--blue)",
  resolved: "var(--green)",
};
const SEV_LABEL = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  resolved: "Resolved",
};

/* ---------------------------------------------------------------
   STYLES
--------------------------------------------------------------- */

const CSS = `
:root{
  --bg:#0B0F14; --surface:#111820; --surface2:#151E28; --line:#232E3A;
  --text:#E8EDF2; --muted:#7C8A99; --muted2:#54626F;
  --amber:#F2A93B; --red:#E5484D; --green:#3DD68C; --blue:#4C9FE8;
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
}
.sw-root{ background:var(--bg); color:var(--text); font-family:var(--sans);
  min-height:100vh; display:flex; font-size:14px; }
.sw-side{ width:208px; flex-shrink:0; background:var(--surface); border-right:1px solid var(--line);
  display:flex; flex-direction:column; padding:18px 12px; gap:2px; }
.sw-brand{ display:flex; align-items:center; gap:9px; padding:6px 10px 20px 10px; }
.sw-brand-mark{ width:28px; height:28px; border-radius:7px; background:linear-gradient(135deg,var(--red),var(--amber));
  display:flex; align-items:center; justify-content:center; flex-shrink:0; }
.sw-brand-name{ font-weight:700; font-size:14.5px; letter-spacing:0.2px; }
.sw-brand-sub{ font-family:var(--mono); font-size:9.5px; color:var(--muted2); letter-spacing:1px; text-transform:uppercase; }
.sw-nav-item{ display:flex; align-items:center; gap:10px; padding:9px 10px; border-radius:8px; cursor:pointer;
  color:var(--muted); font-size:13.2px; font-weight:500; transition:background .15s, color .15s; }
.sw-nav-item:hover{ background:var(--surface2); color:var(--text); }
.sw-nav-item.active{ background:var(--surface2); color:var(--text); }
.sw-nav-item.active svg{ color:var(--amber); }
.sw-side-foot{ margin-top:auto; padding:10px; border-top:1px solid var(--line); }
.sw-status-row{ display:flex; align-items:center; gap:7px; font-family:var(--mono); font-size:10.5px; color:var(--green); }
.sw-dot{ width:6px; height:6px; border-radius:50%; background:var(--green); box-shadow:0 0 0 3px rgba(61,214,140,0.18); }
.sw-main{ flex:1; min-width:0; display:flex; flex-direction:column; }
.sw-topbar{ height:56px; border-bottom:1px solid var(--line); display:flex; align-items:center;
  justify-content:space-between; padding:0 24px; flex-shrink:0; }
.sw-topbar-title{ font-size:15.5px; font-weight:700; }
.sw-topbar-meta{ font-family:var(--mono); font-size:11.5px; color:var(--muted); display:flex; gap:18px; }
.sw-content{ padding:24px; overflow-y:auto; flex:1; }
.sw-grid-stats{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:20px; }
.sw-card{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:16px; }
.sw-stat-label{ font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:0.6px; font-weight:600; }
.sw-stat-value{ font-family:var(--mono); font-size:28px; font-weight:700; margin-top:8px; }
.sw-stat-sub{ font-size:11.5px; color:var(--muted2); margin-top:4px; }
.sw-section-title{ font-size:12.5px; font-weight:700; text-transform:uppercase; letter-spacing:0.6px;
  color:var(--muted); margin-bottom:12px; display:flex; align-items:center; gap:8px; }
.sw-two-col{ display:grid; grid-template-columns:1.3fr 1fr; gap:16px; align-items:start; }
.sw-feed-item{ display:flex; align-items:center; gap:12px; padding:11px 12px; border-radius:8px;
  border:1px solid var(--line); margin-bottom:8px; background:var(--surface); }
.sw-sev-chip{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }
.sw-feed-main{ flex:1; min-width:0; }
.sw-feed-title{ font-size:13px; font-weight:600; }
.sw-feed-loc{ font-size:11.5px; color:var(--muted); margin-top:1px; }
.sw-feed-right{ text-align:right; flex-shrink:0; }
.sw-conf{ font-family:var(--mono); font-size:12px; color:var(--text); }
.sw-time{ font-size:10.5px; color:var(--muted2); margin-top:2px; }
.sw-badge{ display:inline-block; padding:2px 8px; border-radius:20px; font-size:10.5px; font-weight:700;
  font-family:var(--mono); letter-spacing:0.3px; }
.sw-pipeline{ display:flex; align-items:center; }
.sw-pipe-step{ display:flex; flex-direction:column; align-items:center; gap:6px; flex:1; position:relative; }
.sw-pipe-circle{ width:30px; height:30px; border-radius:50%; border:2px solid var(--line);
  display:flex; align-items:center; justify-content:center; background:var(--surface); z-index:1;
  font-family:var(--mono); font-size:11px; color:var(--muted2); transition:all .3s; }
.sw-pipe-circle.done{ border-color:var(--green); color:var(--green); background:rgba(61,214,140,0.08); }
.sw-pipe-circle.now{ border-color:var(--amber); color:var(--amber); background:rgba(242,169,59,0.1);
  box-shadow:0 0 0 4px rgba(242,169,59,0.14); }
.sw-pipe-label{ font-size:10.5px; color:var(--muted); font-weight:600; }
.sw-pipe-label.on{ color:var(--text); }
.sw-pipe-line{ position:absolute; top:15px; left:50%; width:100%; height:2px; background:var(--line); z-index:0; }
.sw-pipe-line.done{ background:var(--green); }
.sw-scenario-btn{ text-align:left; width:100%; background:var(--surface); border:1px solid var(--line);
  border-radius:9px; padding:12px 13px; cursor:pointer; margin-bottom:8px; transition:border-color .15s, background .15s; }
.sw-scenario-btn:hover{ border-color:var(--muted2); }
.sw-scenario-btn.selected{ border-color:var(--amber); background:rgba(242,169,59,0.06); }
.sw-scenario-tag{ font-family:var(--mono); font-size:9.5px; text-transform:uppercase; letter-spacing:0.6px;
  color:var(--muted2); }
.sw-scenario-name{ font-size:13.2px; font-weight:600; margin-top:3px; }
.sw-scenario-sub{ font-size:11.5px; color:var(--muted); margin-top:2px; }
.sw-feed-panel{ background:#05080B; border:1px solid var(--line); border-radius:12px; overflow:hidden;
  aspect-ratio:16/9; position:relative; }
.sw-feed-video{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover;
  display:block; background:#05080B; }
.sw-feed-unavailable{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  font-family:var(--mono); font-size:11px; letter-spacing:0.6px; color:var(--muted2);
  background:#05080B; text-align:center; padding:20px; }
.sw-feed-connecting{ position:absolute; left:50%; top:14px; transform:translateX(-50%);
  font-family:var(--mono); font-size:10.5px; letter-spacing:0.5px; color:var(--amber);
  background:rgba(5,8,11,0.72); border:1px solid rgba(242,169,59,0.4); border-radius:6px;
  padding:6px 12px; text-align:center; line-height:1.5; z-index:2; }
.sw-feed-connecting-error{ color:var(--red); border-color:rgba(229,72,77,0.4); }
.sw-feed-scan{ position:absolute; inset:0;
  background:
    repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0px, rgba(255,255,255,0.025) 1px, transparent 1px, transparent 3px),
    radial-gradient(ellipse at 50% 40%, rgba(76,159,232,0.10), transparent 60%); }
.sw-feed-grid-dot{ position:absolute; width:3px; height:3px; border-radius:50%; background:rgba(124,138,153,0.4); }
.sw-feed-tag{ position:absolute; top:10px; left:12px; font-family:var(--mono); font-size:10.5px;
  color:var(--red); display:flex; align-items:center; gap:6px; }
.sw-feed-tag .rec-dot{ width:6px; height:6px; border-radius:50%; background:var(--red); animation:blink 1.4s infinite; }
.sw-feed-cam{ position:absolute; top:10px; right:12px; font-family:var(--mono); font-size:10px; color:var(--muted); }
.sw-feed-time{ position:absolute; bottom:10px; right:12px; font-family:var(--mono); font-size:10px; color:var(--muted); }
.sw-ai-hud{ position:absolute; left:12px; bottom:10px; max-width:64%; font-family:var(--mono);
  font-size:10px; color:var(--muted); line-height:1.55; background:rgba(5,8,11,0.6);
  padding:7px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.07); backdrop-filter:blur(2px); }
.sw-ai-hud-status{ display:flex; align-items:center; gap:6px; font-size:10.5px; letter-spacing:0.4px;
  color:var(--text); margin-bottom:2px; }
.sw-ai-hud-dot{ width:6px; height:6px; border-radius:50%; flex:none; }
.sw-ai-hud-line{ color:var(--muted); }
.sw-ai-hud-warning{ margin-top:6px; padding:6px 8px; border-radius:5px;
  background:rgba(242,169,59,0.14); border:1px solid rgba(242,169,59,0.4);
  color:var(--amber); font-size:10.5px; line-height:1.5; letter-spacing:0.2px; }
.sw-ai-hud-confirmed{ margin-top:6px; padding:6px 8px; border-radius:5px;
  background:rgba(229,72,77,0.16); border:1px solid rgba(229,72,77,0.45);
  color:var(--red); font-weight:700; font-size:10.5px; line-height:1.5; letter-spacing:0.2px; }
@keyframes blink{ 0%,100%{opacity:1} 50%{opacity:0.15} }
.sw-bbox{ position:absolute; border:2px solid var(--amber); border-radius:3px;
  box-shadow:0 0 0 2000px rgba(0,0,0,0) ; animation:bboxIn .35s ease-out; }
@keyframes bboxIn{ from{ opacity:0; transform:scale(1.08);} to{opacity:1; transform:scale(1);} }
.sw-bbox-label{ position:absolute; top:-20px; left:-2px; background:var(--amber); color:#1a1305;
  font-family:var(--mono); font-size:9.5px; font-weight:700; padding:2px 6px; border-radius:3px; white-space:nowrap; }
.sw-btn{ background:var(--amber); color:#1a1305; border:none; border-radius:8px; padding:10px 18px;
  font-weight:700; font-size:13px; cursor:pointer; display:inline-flex; align-items:center; gap:7px; }
.sw-btn:disabled{ opacity:0.4; cursor:not-allowed; }
.sw-btn-ghost{ background:transparent; color:var(--muted); border:1px solid var(--line); border-radius:8px;
  padding:10px 16px; font-weight:600; font-size:13px; cursor:pointer; display:inline-flex; align-items:center; gap:7px; }
.sw-table{ width:100%; border-collapse:collapse; }
.sw-table th{ text-align:left; font-size:10.5px; text-transform:uppercase; letter-spacing:0.5px; color:var(--muted2);
  padding:0 12px 10px 12px; font-weight:700; border-bottom:1px solid var(--line); }
.sw-table td{ padding:12px; border-bottom:1px solid var(--line); font-size:12.8px; vertical-align:middle; }
.sw-table tr:last-child td{ border-bottom:none; }
.sw-filter-row{ display:flex; gap:8px; margin-bottom:14px; }
.sw-filter-btn{ background:var(--surface); border:1px solid var(--line); color:var(--muted); padding:6px 13px;
  border-radius:20px; font-size:12px; font-weight:600; cursor:pointer; }
.sw-filter-btn.active{ background:var(--surface2); color:var(--text); border-color:var(--muted2); }
.sw-map-wrap{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px; }
.sw-map-svg{ width:100%; height:auto; display:block; border-radius:8px; background:#0D141C; }
.sw-map-legend{ display:flex; gap:16px; margin-top:12px; font-size:11.5px; color:var(--muted); }
.sw-map-legend span{ display:flex; align-items:center; gap:6px; }
.sw-leg-dot{ width:8px; height:8px; border-radius:50%; }
.sw-detail-panel{ position:absolute; top:16px; right:16px; width:220px; background:var(--surface2);
  border:1px solid var(--line); border-radius:10px; padding:14px; font-size:12px; }
.sw-analytics-grid{ display:grid; grid-template-columns:1.4fr 1fr; gap:16px; margin-bottom:16px; }
.sw-loc-row{ display:flex; justify-content:space-between; align-items:center; padding:9px 0;
  border-bottom:1px solid var(--line); font-size:12.6px; }
.sw-loc-row:last-child{ border-bottom:none; }
.sw-loc-count{ font-family:var(--mono); color:var(--amber); font-weight:700; }
`;

/* ---------------------------------------------------------------
   SMALL COMPONENTS
--------------------------------------------------------------- */

function Badge({ severity }) {
  return (
    <span
      className="sw-badge"
      style={{ color: SEV_COLOR[severity], background: `${SEV_COLOR[severity]}1A`, border: `1px solid ${SEV_COLOR[severity]}40` }}
    >
      {SEV_LABEL[severity]}
    </span>
  );
}

function Pipeline({ stageIndex }) {
  // stageIndex: -1 none, 0..3 stage reached
  return (
    <div className="sw-pipeline">
      {STAGES.map((s, i) => {
        const done = i < stageIndex;
        const now = i === stageIndex;
        return (
          <div className="sw-pipe-step" key={s}>
            {i > 0 && <div className={`sw-pipe-line ${i <= stageIndex ? "done" : ""}`} style={{ left: "-50%", width: "100%" }} />}
            <div className={`sw-pipe-circle ${done ? "done" : ""} ${now ? "now" : ""}`}>
              {done ? <CheckCircle2 size={15} /> : i + 1}
            </div>
            <div className={`sw-pipe-label ${done || now ? "on" : ""}`}>{s}</div>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------
   MAIN APP
--------------------------------------------------------------- */

export default function SafeWatchAI() {
  const [tab, setTab] = useState("dashboard");
  const [incidents, setIncidents] = useState([]);
  const [now, setNow] = useState(new Date());
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // monitoring / scenario runner state
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [stage, setStage] = useState(-1); // -1 idle, 0..3
  const [running, setRunning] = useState(false);
  const cancelRef = useRef(false);
  const videoRef = useRef(null);

  const [severityFilter, setSeverityFilter] = useState("all");
  const [selectedMapId, setSelectedMapId] = useState(null);

  // Tracks whether the current scenario's sample video failed to load
  // (e.g. the file isn't present under backend/sample_video/ yet), so
  // the Monitoring panel can fall back to a clear placeholder instead
  // of a broken/black video element.
  const [videoUnavailable, setVideoUnavailable] = useState(false);

  // Real AI pipeline status (YOLO + ByteTrack). Polled while on the
  // Monitoring tab so the indicator reflects the live backend worker.
  const [aiStatus, setAiStatus] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  // Local "no incident" flag for the AI_MODE=demo "Normal Traffic"
  // scenario, which deliberately never calls the incident API.
  const [normalScanDone, setNormalScanDone] = useState(false);

  // Tracks whether the live MJPEG stream has failed to become ready in
  // a reasonable time (or errored) - drives the "AI STREAM UNAVAILABLE"
  // fallback so the panel NEVER goes black; it just keeps showing the
  // plain video underneath instead. See streamReadyTimeoutRef below.
  const [streamFailed, setStreamFailed] = useState(false);
  const streamReadyTimeoutRef = useRef(null);
  // The exact video_source string used for the CURRENT AI run, set
  // once when monitoring starts - used as a stable <img> key so the
  // live stream is never remounted mid-run by an unrelated re-render.
  const [aiRunVideoSource, setAiRunVideoSource] = useState(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const data = await api.getAiStatus();
        if (!cancelled) setAiStatus(data);
      } catch {
        if (!cancelled) setAiStatus(null);
      }
    }
    poll();
    // Polled at 1s (not 2s) specifically so the "CONNECTING TO AI
    // ANALYSIS..." -> live-stream handoff feels responsive rather than
    // leaving the plain video showing a beat longer than it needs to.
    const t = setInterval(poll, 1000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const isRealAiMode = aiStatus?.ai_mode === "real";
  const realAiRunning = isRealAiMode && !!aiStatus?.running;
  const streamReady = !!aiStatus?.stream_ready;

  // The plain <video> file is what's shown until the live AI stream
  // has PROVEN it has a real frame ready (streamReady) - never just
  // because the worker thread has started (realAiRunning). This is
  // the fix for the black-screen regression: swapping to <img src=.../
  // stream> the instant realAiRunning flips true left the image
  // pointed at a stream with nothing in it yet, since YOLO's first
  // (CPU warm-up) inference is often several seconds slower than
  // steady-state.
  const showingPlainVideo = !(isRealAiMode && realAiRunning && streamReady && !streamFailed);
  const streamConnecting = isRealAiMode && realAiRunning && !streamReady && !streamFailed;

  // If the stream doesn't become ready within a generous window (must
  // stay comfortably above the backend's own GET /api/ai/stream
  // startup_timeout), stop waiting and fall back to the plain video
  // with a clear "unavailable" notice instead of an indefinite
  // "connecting" spinner or a black box.
  useEffect(() => {
    if (streamReadyTimeoutRef.current) {
      clearTimeout(streamReadyTimeoutRef.current);
      streamReadyTimeoutRef.current = null;
    }
    if (streamConnecting) {
      streamReadyTimeoutRef.current = setTimeout(() => {
        console.error("[Monitoring] AI stream did not become ready in time");
        setStreamFailed(true);
      }, 18000);
    }
    return () => {
      if (streamReadyTimeoutRef.current) {
        clearTimeout(streamReadyTimeoutRef.current);
        streamReadyTimeoutRef.current = null;
      }
    };
  }, [streamConnecting]);

  async function startRealAi(scn) {
    setAiBusy(true);
    setStreamFailed(false);
    const videoSource = getSampleVideoPath(scn.video);
    setAiRunVideoSource(videoSource);
    try {
      await api.startAi({
        videoSource,
        cameraId: scn.cam,
      });
      setAiStatus(await api.getAiStatus());
    } catch (err) {
      console.error(err);
      setLoadError(err.message);
    } finally {
      setAiBusy(false);
    }
  }

  async function stopRealAi() {
    setAiBusy(true);
    try {
      await api.stopAi();
      setAiStatus(await api.getAiStatus());
    } catch (err) {
      console.error(err);
      setLoadError(err.message);
    } finally {
      setStreamFailed(false);
      setAiRunVideoSource(null);
      setAiBusy(false);
    }
  }

  // Initial load from the backend (GET /api/incidents), replacing the old
  // hardcoded SEED_INCIDENTS array.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getIncidents();
        if (!cancelled) setIncidents(data.incidents.map(mapIncident));
      } catch (err) {
        console.error(err);
        if (!cancelled) setLoadError(err.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => { cancelRef.current = true; }, []);

  const scenario = SCENARIOS.find((s) => s.id === scenarioId);

  // Switching scenarios always starts a fresh monitoring run: reset
  // the "video unavailable" fallback and stop whatever's currently
  // active, so the visible video and the AI worker's source can never
  // point at two different clips at once (spec: "the AI and visible
  // video must correspond to the same source"; "selecting a new video
  // resets the per-video event state").
  useEffect(() => {
    setVideoUnavailable(false);
    setNormalScanDone(false);
    if (realAiRunning) stopRealAi();
    if (running) resetDemo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId]);

  // Drives the AI Detection Pipeline against the real backend:
  //   POST /api/demo/detection  -> Detected
  //   POST /.../verify          -> Verified
  //   POST /.../alert           -> Alerted   (incident now shown in lists)
  //   POST /.../respond         -> Responding
  // The short sleeps between calls are purely cosmetic pacing for the
  // pipeline animation - no simulated work happens on the backend itself.
  //
  // "Normal Traffic" is a deliberate no-op: it never calls the demo
  // incident API at all, so it can never create an incident (spec:
  // "Normal Traffic must not create alerts").
  async function runDetection() {
    if (running) return;
    cancelRef.current = false;
    setRunning(true);
    setStage(-1);
    setNormalScanDone(false);

    if (scenarioId === "normal") {
      // Normal traffic is deliberately a no-op: no incident API calls,
      // no pipeline stage - just a short "monitoring" pause followed
      // by a clear "no incident" result.
      await sleep(1400);
      if (!cancelRef.current) {
        setNormalScanDone(true);
        setRunning(false);
      }
      return;
    }

    try {
      const created = await api.createDemoDetection(scenarioId);
      if (cancelRef.current) return;
      setStage(0);
      await sleep(700);

      const verified = await api.verifyIncident(created.id);
      if (cancelRef.current) return;
      setStage(1);
      await sleep(900);

      const alerted = await api.alertIncident(created.id);
      if (cancelRef.current) return;
      setStage(2);
      setIncidents((prev) => [mapIncident(alerted), ...prev]);
      await sleep(900);

      const responding = await api.respondIncident(created.id);
      if (cancelRef.current) return;
      setStage(3);
      setIncidents((prev) =>
        prev.map((inc) => (inc.id === responding.id ? mapIncident(responding) : inc))
      );
    } catch (err) {
      console.error(err);
      setLoadError(err.message);
    } finally {
      if (!cancelRef.current) setRunning(false);
    }
  }

  function resetDemo() {
    cancelRef.current = true;
    setRunning(false);
    setStage(-1);
    setNormalScanDone(false);
  }

  // The ONE monitoring control for the panel (spec: no separate "Run
  // AI Detection" / "Start Real AI Monitoring" buttons). Real mode
  // starts/stops the actual YOLO+ByteTrack worker on the selected
  // scenario's video; demo mode runs/cancels the existing canned
  // pipeline (or the Normal Traffic no-op above).
  const monitoringActive = isRealAiMode ? realAiRunning : running;
  const monitoringBusy = isRealAiMode ? aiBusy : false;

  // The video must never autoplay on its own - it only starts playing
  // once "START AI MONITORING" is actually clicked, and it stops/rewinds
  // the moment monitoring stops. `showingPlainVideo` (defined above,
  // right next to the stream-readiness logic it depends on) covers
  // both demo mode AND the real-mode "connecting"/"stream failed"
  // states, so the plain video keeps playing under those overlays
  // instead of the panel ever going black.
  useEffect(() => {
    const el = videoRef.current;
    if (!el || !showingPlainVideo) return;
    if (monitoringActive) {
      el.play().catch(() => { /* autoplay-policy rejections are fine to ignore here */ });
    } else {
      el.pause();
      el.currentTime = 0;
    }
  }, [monitoringActive, showingPlainVideo]);

  async function toggleMonitoring() {
    if (isRealAiMode) {
      if (realAiRunning) {
        await stopRealAi();
      } else {
        await startRealAi(scenario);
      }
    } else if (running) {
      resetDemo();
    } else {
      runDetection();
    }
  }

  // Drives the "AI MONITORING: IDLE / STARTING / ACTIVE / ERROR" text
  // in the HUD. Real mode reflects the AI worker's actual state
  // machine; demo mode only ever needs idle/active since there's no
  // model to load or camera to open.
  const hudState = isRealAiMode
    ? (aiStatus?.state || "idle")
    : (running ? "active" : "idle");

  // --- Stage 1 (pre-accident warning) vs Stage 2 (accident confirmed) ---
  // These are deliberately separate booleans, never merged into one
  // "alert" flag: a prediction is not an incident (see backend
  // services/risk_predictor.py), so the UI must never let a warning
  // read as if the accident already happened, or vice versa.
  const isAccidentConfirmed = isRealAiMode
    ? !!aiStatus?.incident_confirmed
    : (scenarioId !== "normal" && stage >= 2);

  // Real mode only - demo mode has no real physics behind it, so it
  // never fabricates a pre-accident warning (see spec: "Do not fake
  // pre-accident detection").
  const isPredictionActive = isRealAiMode && !isAccidentConfirmed && !!aiStatus?.prediction_active;

  const confirmedText = isRealAiMode
    ? friendlyDetectionLabel(aiStatus?.last_detection)
    : (scenarioId === "normal" ? null : friendlyDetectionLabel(scenario.label));

  const RISK_TYPE_LABEL = {
    vehicle_collision: "VEHICLE COLLISION RISK",
    two_wheeler_collision: "TWO-WHEELER COLLISION RISK",
    safety: "WOMEN SAFETY RISK",
  };
  const predictionRiskLabel = RISK_TYPE_LABEL[aiStatus?.risk_type] || "COLLISION RISK";

  const showNoIncidentText = isRealAiMode
    ? (realAiRunning && !isAccidentConfirmed && !isPredictionActive && aiStatus?.frames_processed > 0 && scenarioId === "normal")
    : (scenarioId === "normal" && normalScanDone);


  const stats = useMemo(() => {
    const active = incidents.filter((i) => i.status !== "Responding" || i.severity !== "resolved").length;
    const activeReal = incidents.filter((i) => i.severity !== "resolved").length;
    const accidents = incidents.filter((i) => i.category === "accident").length;
    const safety = incidents.filter((i) => i.category === "safety").length;
    return { activeReal, accidents, safety, total: incidents.length };
  }, [incidents]);

  const feedSorted = useMemo(
    () => [...incidents].sort((a, b) => b.time - a.time),
    [incidents]
  );

  const currentPipelineIncident = feedSorted[0];

  const filteredIncidents = useMemo(
    () => (severityFilter === "all" ? feedSorted : feedSorted.filter((i) => i.severity === severityFilter)),
    [feedSorted, severityFilter]
  );

  const byTypeData = useMemo(() => {
    const map = {};
    incidents.forEach((i) => {
      map[i.label] = (map[i.label] || 0) + 1;
    });
    return Object.entries(map).map(([name, count]) => ({ name, count }));
  }, [incidents]);

  const responseTrend = [
    { t: "-6h", mins: 9.2 },
    { t: "-5h", mins: 8.4 },
    { t: "-4h", mins: 7.9 },
    { t: "-3h", mins: 6.6 },
    { t: "-2h", mins: 5.8 },
    { t: "-1h", mins: 5.1 },
    { t: "now", mins: 4.3 },
  ];

  const highRisk = useMemo(() => {
    const map = {};
    incidents.forEach((i) => {
      map[i.location] = (map[i.location] || 0) + 1;
    });
    return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [incidents]);

  const NAV = [
    { id: "dashboard", label: "Dashboard", icon: LayoutGrid },
    { id: "monitoring", label: "Monitoring", icon: Video },
    { id: "incidents", label: "Incidents", icon: AlertTriangle },
    { id: "map", label: "Incident Map", icon: MapPin },
    { id: "analytics", label: "Analytics", icon: BarChart3 },
  ];

  return (
    <div className="sw-root">
      <style>{CSS}</style>

      {/* SIDEBAR */}
      <div className="sw-side">
        <div className="sw-brand">
          <div className="sw-brand-mark"><ShieldAlert size={16} color="#0B0F14" /></div>
          <div>
            <div className="sw-brand-name">EagleWatch AI</div>
            <div className="sw-brand-sub">AI-POWERED PUBLIC SAFETY</div>
          </div>
        </div>
        {NAV.map((n) => (
          <div key={n.id} className={`sw-nav-item ${tab === n.id ? "active" : ""}`} onClick={() => setTab(n.id)}>
            <n.icon size={16} />
            {n.label}
          </div>
        ))}
        <div className="sw-side-foot">
          <div className="sw-status-row"><div className="sw-dot" /> AI SYSTEM ARMED</div>
        </div>
      </div>

      {/* MAIN */}
      <div className="sw-main">
        <div className="sw-topbar">
          <div className="sw-topbar-title">
            {NAV.find((n) => n.id === tab)?.label}
          </div>
          <div className="sw-topbar-meta">
            {loading && <span>Connecting to backend…</span>}
            {!loading && loadError && (
              <span style={{ color: "var(--red)" }} title={loadError}>
                Backend unreachable
              </span>
            )}
            <span>{stats.activeReal} active incidents</span>
            <span>{clockStr(now)} IST</span>
          </div>
        </div>

        <div className="sw-content">
          {tab === "dashboard" && (
            <>
              <div className="sw-grid-stats">
                <div className="sw-card">
                  <div className="sw-stat-label">Active Incidents</div>
                  <div className="sw-stat-value" style={{ color: "var(--red)" }}>{stats.activeReal}</div>
                  <div className="sw-stat-sub">Across {new Set(incidents.map((i) => i.location)).size} monitored zones</div>
                </div>
                <div className="sw-card">
                  <div className="sw-stat-label">Accidents Detected</div>
                  <div className="sw-stat-value">{stats.accidents}</div>
                  <div className="sw-stat-sub">Collisions & two-wheeler falls</div>
                </div>
                <div className="sw-card">
                  <div className="sw-stat-label">Safety Events</div>
                  <div className="sw-stat-value">{stats.safety}</div>
                  <div className="sw-stat-sub">Distress & pursuit patterns</div>
                </div>
                <div className="sw-card">
                  <div className="sw-stat-label">Avg. Response Time</div>
                  <div className="sw-stat-value" style={{ color: "var(--green)" }}>4.3<span style={{fontSize:14, color:"var(--muted)"}}> min</span></div>
                  <div className="sw-stat-sub">Down from 9.2 min, 6h ago</div>
                </div>
              </div>

              <div className="sw-two-col">
                <div className="sw-card">
                  <div className="sw-section-title"><Radio size={13} /> Recent AI Detections</div>
                  {feedSorted.slice(0, 6).map((inc) => (
                    <div className="sw-feed-item" key={inc.id}>
                      <div className="sw-sev-chip" style={{ background: SEV_COLOR[inc.severity] }} />
                      <div className="sw-feed-main">
                        <div className="sw-feed-title">{inc.label}</div>
                        <div className="sw-feed-loc">{inc.location}</div>
                      </div>
                      <div className="sw-feed-right">
                        <div className="sw-conf">{inc.confidence}%</div>
                        <div className="sw-time">{timeAgo(inc.time)}</div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="sw-card">
                  <div className="sw-section-title"><Activity size={13} /> Live Incident Status</div>
                  {currentPipelineIncident && (
                    <>
                      <div style={{ marginBottom: 18 }}>
                        <div style={{ fontWeight: 700, fontSize: 13.5 }}>{currentPipelineIncident.label}</div>
                        <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 2 }}>{currentPipelineIncident.location}</div>
                      </div>
                      <Pipeline
                        stageIndex={
                          currentPipelineIncident.status === "Responding" ? 3 :
                          currentPipelineIncident.status === "Alerted" ? 2 :
                          currentPipelineIncident.status === "Verified" ? 1 : 0
                        }
                      />
                    </>
                  )}
                </div>
              </div>
            </>
          )}

          {tab === "monitoring" && (
            <div className="sw-two-col">
              <div>
                <div className="sw-card" style={{ padding: 10 }}>
                  <div className="sw-feed-panel">
                    {showingPlainVideo ? (
                      !videoUnavailable ? (
                        <video
                          key={scenario.video}
                          ref={videoRef}
                          src={getVideoUrl(scenario.video)}
                          muted
                          loop
                          playsInline
                          preload="auto"
                          className="sw-feed-video"
                          onError={() => {
                            console.error(
                              `[Monitoring] Sample video unavailable: ${scenario.video} ` +
                              `(expected at backend/sample_video/${scenario.video})`
                            );
                            setVideoUnavailable(true);
                          }}
                        />
                      ) : (
                        <div className="sw-feed-unavailable">CCTV VIDEO UNAVAILABLE</div>
                      )
                    ) : (
                      /* REAL AI MONITORING IS RUNNING AND THE STREAM HAS
                         PROVEN IT HAS A FRAME (streamReady): swap the
                         plain file for the live, AI-annotated MJPEG
                         stream (GET /api/ai/stream). Every frame shown
                         here is a frame the worker just finished
                         processing, so this plays back at exactly the
                         AI's real processing FPS, with real YOLO boxes/
                         track IDs/confidence already burned in
                         server-side. `key` is the video_source captured
                         once when this run started - not the polled
                         status object - so this never remounts mid-run. */
                      <img
                        key={aiRunVideoSource || scenario.video}
                        src={getAiStreamUrl()}
                        alt="Live AI-annotated CCTV feed"
                        className="sw-feed-video"
                        onError={() => {
                          console.error("[Monitoring] AI stream errored - falling back to the plain video");
                          setStreamFailed(true);
                        }}
                      />
                    )}

                    {/* Never a black screen: while the live stream is
                        still warming up (YOLO's first inference is
                        commonly several seconds slower than steady
                        state), or if it failed outright, the plain
                        video above keeps playing with a small status
                        badge on top instead. */}
                    {streamConnecting && (
                      <div className="sw-feed-connecting">CONNECTING TO AI ANALYSIS...</div>
                    )}
                    {streamFailed && (
                      <div className="sw-feed-connecting sw-feed-connecting-error">
                        AI STREAM UNAVAILABLE<br />Showing original CCTV feed
                      </div>
                    )}

                    <div className="sw-feed-scan" />
                    {[...Array(14)].map((_, i) => (
                      <div key={i} className="sw-feed-grid-dot" style={{ left: `${(i * 37) % 96}%`, top: `${(i * 53) % 92}%` }} />
                    ))}
                    <div className="sw-feed-tag"><div className="rec-dot" /> LIVE AI FEED · AI ANALYSIS ACTIVE</div>
                    <div className="sw-feed-cam">{scenario.cam}</div>
                    <div className="sw-feed-time">{clockStr(now)}</div>

                    {/* DEMO MODE fallback only: a single illustrative
                        detection box for the canned scenario pipeline.
                        Never shown in AI_MODE=real (real mode's boxes
                        come from the AI stream above, already frame-
                        locked to the AI's own FPS) and never shown for
                        Normal Traffic. */}
                    {!isRealAiMode && stage >= 0 && scenarioId !== "normal" && (
                      <div className="sw-bbox" style={{ left: "38%", top: "34%", width: "26%", height: "38%" }}>
                        <div className="sw-bbox-label">AI DETECTED · {scenario.label} · {scenario.confidence}%</div>
                      </div>
                    )}

                    {/* ONE integrated AI HUD - merges what used to be a
                        separate "Real AI Monitoring" card into the CCTV
                        panel itself. Values are dynamic in real mode
                        (from GET /api/ai/status) and shown as "—" in
                        demo mode rather than being faked. */}
                    <div className="sw-ai-hud">
                      <div className="sw-ai-hud-status">
                        <span
                          className="sw-ai-hud-dot"
                          style={{
                            background:
                              hudState === "active" ? "var(--green)" :
                              hudState === "starting" ? "var(--amber)" :
                              hudState === "error" ? "var(--red)" : "var(--muted2)",
                          }}
                        />
                        AI MONITORING: {hudState.toUpperCase()}
                      </div>
                      <div className="sw-ai-hud-line">YOLO11n · ByteTrack</div>
                      <div className="sw-ai-hud-line">
                        FPS: {isRealAiMode && realAiRunning ? aiStatus.fps : "—"} · OBJECTS: {isRealAiMode && realAiRunning ? aiStatus.objects_tracked : "—"}
                      </div>

                      {/* STAGE 2: accident confirmed - always takes
                          visual priority over a stale prediction. */}
                      {isAccidentConfirmed && confirmedText && (
                        <div className="sw-ai-hud-confirmed">
                          🔴 ACCIDENT CONFIRMED<br />
                          {confirmedText}
                        </div>
                      )}

                      {/* STAGE 1: pre-accident warning - real mode
                          only, and only while nothing has been
                          confirmed yet. Numbers come straight from
                          GET /api/ai/status (risk_level/
                          collision_probability/time_to_collision),
                          never fabricated in the frontend. */}
                      {!isAccidentConfirmed && isPredictionActive && (
                        <div className="sw-ai-hud-warning">
                          🟡 PRE-ACCIDENT WARNING<br />
                          {predictionRiskLabel}<br />
                          Risk: {aiStatus.risk_level.replace("_RISK", "")} · Probability: {Math.round(aiStatus.collision_probability * 100)}%
                          {aiStatus.time_to_collision != null && <> · TTC: {aiStatus.time_to_collision.toFixed(1)}s</>}
                        </div>
                      )}

                      {showNoIncidentText && (
                        <div className="sw-ai-hud-line" style={{ marginTop: 4 }}>NO INCIDENT</div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="sw-card" style={{ marginTop: 14 }}>
                  <div className="sw-section-title"><Siren size={13} /> AI Detection Pipeline</div>

                  {isRealAiMode ? (
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--muted)", marginBottom: 4 }}>
                      <div>Model: {aiStatus?.model || "yolo11n.pt"}</div>
                      <div>Tracker: {aiStatus?.tracker || "bytetrack.yaml"}</div>
                      <div>Device: {(aiStatus?.device || "cpu").toString().toUpperCase()}</div>
                      <div>Source: {scenario.video}</div>
                    </div>
                  ) : (
                    <Pipeline stageIndex={scenarioId === "normal" ? -1 : stage} />
                  )}

                  {isRealAiMode && (aiStatus?.model_load_error || aiStatus?.start_error) && (
                    <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--red)" }}>
                      {aiStatus.model_load_error || aiStatus.start_error}
                    </div>
                  )}

                  <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
                    <button className="sw-btn" onClick={toggleMonitoring} disabled={monitoringBusy}>
                      {monitoringActive ? (<><Square size={14} /> STOP AI MONITORING</>) : (<><Play size={14} /> START AI MONITORING</>)}
                    </button>
                  </div>
                </div>
              </div>

              <div className="sw-card">
                <div className="sw-section-title"><Video size={13} /> AI Scenario Library</div>
                {SCENARIOS.map((s) => (
                  <div
                    key={s.id}
                    className={`sw-scenario-btn ${scenarioId === s.id ? "selected" : ""}`}
                    onClick={() => { if (!monitoringActive) { setScenarioId(s.id); setStage(-1); } }}
                  >
                    <div className="sw-scenario-tag">
                      {s.category === "accident" ? (
                        <><Car size={10} style={{display:"inline", marginRight:4, verticalAlign:-1}}/>Accident</>
                      ) : s.category === "safety" ? (
                        <><ShieldAlert size={10} style={{display:"inline", marginRight:4, verticalAlign:-1}}/>Women's Safety</>
                      ) : (
                        <><Activity size={10} style={{display:"inline", marginRight:4, verticalAlign:-1}}/>Baseline</>
                      )}
                    </div>
                    <div className="sw-scenario-name">{s.label}</div>
                    <div className="sw-scenario-sub">{s.sub} · {s.location}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {tab === "incidents" && (
            <div className="sw-card">
              <div className="sw-filter-row">
                {["all", "critical", "high", "medium", "resolved"].map((f) => (
                  <button key={f} className={`sw-filter-btn ${severityFilter === f ? "active" : ""}`} onClick={() => setSeverityFilter(f)}>
                    {f === "all" ? "All" : SEV_LABEL[f]}
                  </button>
                ))}
              </div>
              <table className="sw-table">
                <thead>
                  <tr>
                    <th>Incident</th><th>Location</th><th>Severity</th><th>AI Confidence</th><th>Status</th><th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredIncidents.map((inc) => (
                    <tr key={inc.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{inc.label}</div>
                        <div style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: "var(--muted2)" }}>{inc.id}</div>
                      </td>
                      <td style={{ color: "var(--muted)" }}>{inc.location}</td>
                      <td><Badge severity={inc.severity} /></td>
                      <td style={{ fontFamily: "var(--mono)" }}>{inc.confidence}%</td>
                      <td style={{ color: "var(--muted)" }}>{inc.status}</td>
                      <td style={{ color: "var(--muted2)", fontSize: 11.5 }}>{timeAgo(inc.time)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === "map" && (
            <div className="sw-map-wrap" style={{ position: "relative" }}>
              <svg className="sw-map-svg" viewBox="0 0 100 60" preserveAspectRatio="none">
                <defs>
                  <pattern id="grid" width="5" height="5" patternUnits="userSpaceOnUse">
                    <path d="M 5 0 L 0 0 0 5" fill="none" stroke="#1B2530" strokeWidth="0.3" />
                  </pattern>
                </defs>
                <rect width="100" height="60" fill="url(#grid)" />
                {[10, 25, 40, 55, 70, 85].map((x) => <line key={x} x1={x} y1="0" x2={x - 8} y2="60" stroke="#232E3A" strokeWidth="0.6" />)}
                {incidents.map((inc) => (
                  <g key={inc.id} onClick={() => setSelectedMapId(inc.id)} style={{ cursor: "pointer" }}>
                    {inc.severity === "critical" && (
                      <circle cx={inc.x} cy={inc.y * 0.6} r="3.2" fill={SEV_COLOR[inc.severity]} opacity="0.25">
                        <animate attributeName="r" values="2.5;5;2.5" dur="1.8s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.3;0;0.3" dur="1.8s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle cx={inc.x} cy={inc.y * 0.6} r="1.8" fill={SEV_COLOR[inc.severity]} stroke="#05080B" strokeWidth="0.5" />
                  </g>
                ))}
              </svg>

              {selectedMapId && (() => {
                const inc = incidents.find((i) => i.id === selectedMapId);
                if (!inc) return null;
                return (
                  <div className="sw-detail-panel">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                      <div style={{ fontWeight: 700, fontSize: 12.5 }}>{inc.label}</div>
                      <X size={13} style={{ cursor: "pointer", color: "var(--muted)" }} onClick={() => setSelectedMapId(null)} />
                    </div>
                    <div style={{ color: "var(--muted)", marginTop: 4 }}>{inc.location}</div>
                    <div style={{ marginTop: 8 }}><Badge severity={inc.severity} /></div>
                    <div style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 11 }}>Confidence: {inc.confidence}%</div>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--muted)" }}>{inc.status} · {timeAgo(inc.time)}</div>
                  </div>
                );
              })()}

              <div className="sw-map-legend">
                {Object.entries(SEV_LABEL).map(([k, v]) => (
                  <span key={k}><span className="sw-leg-dot" style={{ background: SEV_COLOR[k] }} />{v}</span>
                ))}
              </div>
            </div>
          )}

          {tab === "analytics" && (
            <>
              <div className="sw-analytics-grid">
                <div className="sw-card">
                  <div className="sw-section-title"><BarChart3 size={13} /> Incidents by Type</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={byTypeData} margin={{ left: -20 }}>
                      <CartesianGrid stroke="#1B2530" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: "#7C8A99", fontSize: 10 }} interval={0} angle={-12} textAnchor="end" height={50} />
                      <YAxis tick={{ fill: "#7C8A99", fontSize: 11 }} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: "#151E28", border: "1px solid #232E3A", fontSize: 12 }} />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {byTypeData.map((_, i) => <Cell key={i} fill={["#F2A93B", "#E5484D", "#4C9FE8", "#3DD68C"][i % 4]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="sw-card">
                  <div className="sw-section-title"><Clock size={13} /> Response Time Trend</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={responseTrend} margin={{ left: -20 }}>
                      <defs>
                        <linearGradient id="respGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#3DD68C" stopOpacity={0.4} />
                          <stop offset="100%" stopColor="#3DD68C" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#1B2530" vertical={false} />
                      <XAxis dataKey="t" tick={{ fill: "#7C8A99", fontSize: 11 }} />
                      <YAxis tick={{ fill: "#7C8A99", fontSize: 11 }} unit="m" />
                      <Tooltip contentStyle={{ background: "#151E28", border: "1px solid #232E3A", fontSize: 12 }} />
                      <Area type="monotone" dataKey="mins" stroke="#3DD68C" fill="url(#respGrad)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="sw-card">
                <div className="sw-section-title"><MapPin size={13} /> High-Risk Locations</div>
                {highRisk.map(([loc, count]) => (
                  <div className="sw-loc-row" key={loc}>
                    <span>{loc}</span>
                    <span className="sw-loc-count">{count} incident{count > 1 ? "s" : ""}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
