import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  LayoutGrid, Video, AlertTriangle, MapPin, BarChart3, ShieldAlert, Car,
  Radio, Clock, CheckCircle2, Siren, Activity, X, Play, RotateCcw
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  AreaChart, Area, Cell
} from "recharts";

/* ---------------------------------------------------------------
   DATA
--------------------------------------------------------------- */

const STAGES = ["Detected", "Verified", "Alerted", "Responding"];

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
  },
  {
    id: "twowheeler",
    category: "accident",
    label: "Two-Wheeler Fall",
    sub: "Single-vehicle loss of control",
    location: "ECR Coastal Road, KM 12",
    cam: "CAM-11",
    confidence: 88,
    severity: "high",
  },
  {
    id: "distress",
    category: "safety",
    label: "Potential Distress Signal",
    sub: "Isolated individual, erratic motion",
    location: "T Nagar Bus Terminus",
    cam: "CAM-07",
    confidence: 91,
    severity: "critical",
  },
  {
    id: "chasing",
    category: "safety",
    label: "Suspicious Pursuit Pattern",
    sub: "Sustained follow behaviour detected",
    location: "Velachery Underpass",
    cam: "CAM-19",
    confidence: 86,
    severity: "high",
  },
];

const SEED_INCIDENTS = [
  { id: "INC-2291", category: "accident", label: "Vehicle Collision", location: "Kathipara Flyover", severity: "resolved", confidence: 92, status: "Responding", time: mins(240), x: 62, y: 58 },
  { id: "INC-2294", category: "safety", label: "Potential Distress Signal", location: "Guindy Metro Exit", severity: "resolved", confidence: 89, status: "Responding", time: mins(190), x: 47, y: 40 },
  { id: "INC-2299", category: "accident", label: "Two-Wheeler Fall", location: "OMR Sholinganallur", severity: "medium", confidence: 81, status: "Alerted", time: mins(96), x: 78, y: 71 },
  { id: "INC-2302", category: "safety", label: "Suspicious Pursuit Pattern", location: "Velachery Underpass", severity: "high", confidence: 87, status: "Verified", time: mins(41), x: 55, y: 66 },
  { id: "INC-2305", category: "accident", label: "Vehicle Collision", location: "Anna Salai & Mount Rd Jn", severity: "critical", confidence: 95, status: "Responding", time: mins(12), x: 40, y: 33 },
  { id: "INC-2307", category: "safety", label: "Potential Distress Signal", location: "T Nagar Bus Terminus", severity: "critical", confidence: 90, status: "Alerted", time: mins(4), x: 35, y: 52 },
];

function mins(n) {
  return new Date(Date.now() - n * 60000);
}
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
  const [incidents, setIncidents] = useState(SEED_INCIDENTS);
  const [now, setNow] = useState(new Date());

  // monitoring / scenario runner state
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [stage, setStage] = useState(-1); // -1 idle, 0..3
  const [running, setRunning] = useState(false);
  const timers = useRef([]);

  const [severityFilter, setSeverityFilter] = useState("all");
  const [selectedMapId, setSelectedMapId] = useState(null);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const scenario = SCENARIOS.find((s) => s.id === scenarioId);

  function runDetection() {
    if (running) return;
    setRunning(true);
    setStage(-1);
    const delays = [500, 1400, 2300, 3200];
    timers.current.forEach(clearTimeout);
    timers.current = delays.map((d, i) =>
      setTimeout(() => {
        setStage(i);
        if (i === 2) {
          // on "Alerted" -> create incident
          const jitter = Math.floor(Math.random() * 4) - 2;
          const newInc = {
            id: `INC-${Math.floor(2300 + Math.random() * 700)}`,
            category: scenario.category,
            label: scenario.label,
            location: scenario.location,
            severity: scenario.severity,
            confidence: Math.min(99, scenario.confidence + jitter),
            status: "Alerted",
            time: new Date(),
            x: 30 + Math.random() * 45,
            y: 30 + Math.random() * 45,
          };
          setIncidents((prev) => [newInc, ...prev]);
        }
        if (i === 3) {
          setIncidents((prev) =>
            prev.map((inc, idx) => (idx === 0 ? { ...inc, status: "Responding" } : inc))
          );
          setRunning(false);
        }
      }, d)
    );
  }

  function resetDemo() {
    timers.current.forEach(clearTimeout);
    setRunning(false);
    setStage(-1);
  }

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
            <div className="sw-brand-name">SafeWatch AI</div>
            <div className="sw-brand-sub">Public Safety Intel</div>
          </div>
        </div>
        {NAV.map((n) => (
          <div key={n.id} className={`sw-nav-item ${tab === n.id ? "active" : ""}`} onClick={() => setTab(n.id)}>
            <n.icon size={16} />
            {n.label}
          </div>
        ))}
        <div className="sw-side-foot">
          <div className="sw-status-row"><div className="sw-dot" /> SYSTEM ARMED</div>
        </div>
      </div>

      {/* MAIN */}
      <div className="sw-main">
        <div className="sw-topbar">
          <div className="sw-topbar-title">
            {NAV.find((n) => n.id === tab)?.label}
          </div>
          <div className="sw-topbar-meta">
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
                  <div className="sw-section-title"><Radio size={13} /> Recent Incident Feed</div>
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
                  <div className="sw-section-title"><Activity size={13} /> Current Incident Status</div>
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
                    <div className="sw-feed-scan" />
                    {[...Array(14)].map((_, i) => (
                      <div key={i} className="sw-feed-grid-dot" style={{ left: `${(i * 37) % 96}%`, top: `${(i * 53) % 92}%` }} />
                    ))}
                    <div className="sw-feed-tag"><div className="rec-dot" /> SIMULATED FEED</div>
                    <div className="sw-feed-cam">{scenario.cam}</div>
                    <div className="sw-feed-time">{clockStr(now)}</div>
                    {stage >= 0 && (
                      <div className="sw-bbox" style={{ left: "38%", top: "34%", width: "26%", height: "38%" }}>
                        <div className="sw-bbox-label">{scenario.label} · {scenario.confidence}%</div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="sw-card" style={{ marginTop: 14 }}>
                  <div className="sw-section-title"><Siren size={13} /> Detection Pipeline</div>
                  <Pipeline stageIndex={stage} />
                  <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
                    <button className="sw-btn" onClick={runDetection} disabled={running}>
                      <Play size={14} /> Run Detection
                    </button>
                    <button className="sw-btn-ghost" onClick={resetDemo}>
                      <RotateCcw size={14} /> Reset
                    </button>
                  </div>
                </div>
              </div>

              <div className="sw-card">
                <div className="sw-section-title"><Video size={13} /> Scenario Library</div>
                {SCENARIOS.map((s) => (
                  <div
                    key={s.id}
                    className={`sw-scenario-btn ${scenarioId === s.id ? "selected" : ""}`}
                    onClick={() => { if (!running) { setScenarioId(s.id); setStage(-1); } }}
                  >
                    <div className="sw-scenario-tag">{s.category === "accident" ? <><Car size={10} style={{display:"inline", marginRight:4, verticalAlign:-1}}/>Accident</> : <><ShieldAlert size={10} style={{display:"inline", marginRight:4, verticalAlign:-1}}/>Women's Safety</>}</div>
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
