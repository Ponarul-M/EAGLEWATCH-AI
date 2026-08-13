# EagleWatch AI

A full-stack hackathon prototype: React/Vite frontend + FastAPI/SQLite
backend, now with a **real AI computer-vision pipeline** (YOLO object
detection + ByteTrack tracking + rule-based temporal event reasoning).

```
eaglewatch-ai/
├── backend/     FastAPI + SQLite API + AI pipeline
└── frontend/    React + Vite dashboard (unchanged UI/UX)
```

The original demo pipeline (`POST /api/demo/detection` + the Detected →
Verified → Alerted → Responding walk-through) still exists exactly as
before, untouched, as a reliability fallback. The real pipeline is
purely additive.

---

## 1. Architecture

```
Camera / Video (webcam or file)
        ↓
OpenCV frame capture
        ↓
YOLO detection            <- real ML: Ultralytics YOLO (yolo11n.pt by default)
        ↓
ByteTrack tracking        <- real CV tracking: object identity across frames
        ↓
Event Analyzer            <- transparent, rule-based temporal logic (NOT ML)
        ↓
Confidence + Severity     <- deterministic, derived from real signals only
        ↓
Cooldown / dedup check
        ↓
FastAPI -> incident_service.create_incident_from_ai()
        ↓
SQLite
        ↓
React Dashboard (unchanged contract: id, category, label, sub, location,
                  camera_id, confidence, severity, status, x, y, time)
```

### What's actually "AI" here, and what isn't

| Layer | What it is |
|---|---|
| YOLO detection | Real object detection model (Ultralytics) |
| ByteTrack | Real multi-object tracking (via `model.track(tracker="bytetrack.yaml")`) |
| Event Analyzer | **Rule-based** temporal logic (bounding-box overlap, speed change, aspect-ratio change, sustained proximity) - not a learned model |
| Severity / Confidence | Deterministic functions of the above signals - never random |

YOLO cannot "understand" a collision or a crime. It detects and tracks
objects; the event analyzer decides what a pattern of tracked-object
motion *might* mean, using explainable rules documented in
`backend/services/event_analyzer.py`.

---

## 2. Two-stage pipeline: prediction vs confirmation

The AI pipeline now has two independent stages, and they never get
merged into a single "alert" concept:

```
YOLO + ByteTrack (unchanged)
        |
        +--> Stage 1: services/risk_predictor.py  (NEW)
        |    "Are these objects on a converging course?"
        |    -> risk_level / collision_probability / time_to_collision
        |    -> NEVER creates an incident
        |
        +--> Stage 2: services/event_analyzer.py  (UNCHANGED)
             "Did the accident/fall/pursuit actually happen?"
             -> confirmed event -> incident_service.create_incident_from_ai()
             -> exactly ONE incident per video run (unchanged)
```

Both stages run every frame, on the exact same `tracks`/`history` from
the exact same YOLO+ByteTrack output - `services/ai_worker.py` just
calls both (see `_process_frame`). Nothing about Stage 2 changed.

### Files modified / added for this feature

| File | Change |
|---|---|
| `backend/services/risk_predictor.py` | **New.** `PreAccidentPredictor` class - Stage 1 (see below). |
| `backend/ai_config.py` | Added `RISK_CONFIRM_FRAMES`, `TTC_HORIZON_SECONDS`, `COLLISION_DISTANCE_PX`, `MIN_CLOSING_SPEED_PX_S`. |
| `backend/services/ai_worker.py` | Calls `risk_predictor.predict()` every frame; stores risk fields; freezes them to `ACCIDENT_CONFIRMED` when Stage 2 confirms; resets risk state on `start()`; extended `_render_preview()` to draw risk connecting-lines/TTC text; extended `status()` with the new fields; added frame/TTC/risk debug logging. |
| `backend/routes/ai.py` | No changes needed - `GET /api/ai/status` already returns whatever `ai_worker.status()` produces, so the new fields are automatically exposed. |
| `backend/.env.example` | Added the four new risk-tuning variables. |
| `backend/tests/test_risk_predictor.py` | **New.** 9 tests covering the physics (see below). |
| `backend/tests/test_ai_worker.py` | Added tests for risk-field population and the freeze-on-confirmation behavior; extended `test_status_shape`. |
| `frontend/src/App.jsx` | HUD now renders two visually distinct states - 🟡 pre-accident warning vs 🔴 accident confirmed - driven entirely by the new `GET /api/ai/status` fields. |

Nothing in `event_analyzer.py`, `severity_service.py`, `detection_service.py`,
`tracking_service.py`, `incident_service.py`, the database schema, or
any existing route was changed.

### The prediction algorithm (Stage 1)

For every pair of currently-tracked vehicles/two-wheelers, `risk_predictor.py`:

1. Estimates each object's velocity vector from its recent position
   history (`tracking_service`'s existing per-track history - no new
   tracking, just math on what's already collected).
2. Computes the relative position `d` and relative velocity `rv`
   between the pair.
3. Solves for the time of closest approach assuming both keep moving
   in a straight line at their current velocity:
   `t* = -(d . rv) / |rv|^2`
4. If `t*` is negative, they're separating (already passed each other,
   or diverging) - **skipped immediately**, no further computation.
5. If `t*` is positive, projects both positions forward by `t*` and
   measures the predicted minimum distance between them.
6. Combines the projected minimum distance and `t*` into a
   `collision_probability` (0.0-1.0) and a risk level
   (`MEDIUM_RISK`/`HIGH_RISK`/`CRITICAL_RISK`), both **deterministic
   functions of the physics above - never random, never a lookup on
   frame number or filename.**

The **women's safety** signal uses a different, honestly-scoped
heuristic: two people's proximity, how similar their direction of
travel is, and how long that's persisted. This is explicitly *not*
claimed to detect intent - the HUD's reason text and this README both
say so. If the video doesn't give the tracker anything better than
"two people near each other," that's exactly and only what gets
reported.

### How TTC is calculated

`time_to_collision` **is** `t*` from step 3 above - the time until the
two objects' predicted paths bring them closest together, using only
their currently-observed velocities. It is `None` whenever there's no
meaningful convergence (parallel motion, diverging motion, or objects
too far apart / too slow relative to each other to say anything useful
- see `ai_config.MIN_CLOSING_SPEED_PX_S`).

### How false positives are reduced

1. **The physics itself filters most of it.** Two vehicles moving in
   formation at the same speed have `rv ~= 0`, so `t*` is undefined/
   skipped outright - this is exactly the "two cars driving side by
   side" case from the spec, and it's excluded by the math, not a
   special-cased rule.
2. **A car that has already passed is excluded.** `t* < 0` means the
   closest approach was in the past - skipped immediately, regardless
   of current distance.
3. **A horizon cutoff.** Predictions further out than
   `TTC_HORIZON_SECONDS` (default 4s) or with a projected minimum
   distance beyond `COLLISION_DISTANCE_PX * 2.5` are discarded as too
   speculative to report.
4. **Temporal debouncing**, exactly analogous to Stage 2's
   `EVENT_CONFIRM_FRAMES`: a risk candidate must hold for
   `RISK_CONFIRM_FRAMES` consecutive frames before it's reported, and
   loses one frame of "credit" per frame it's absent (not reset to
   zero instantly) - see `PreAccidentPredictor.predict()`. One noisy
   frame can't trigger or immediately cancel a warning.

### How prediction differs from confirmation

| | Stage 1 (prediction) | Stage 2 (confirmation) |
|---|---|---|
| Module | `risk_predictor.py` (new) | `event_analyzer.py` (unchanged) |
| Question | "Are they converging?" | "Did it happen?" |
| Signal | velocity, trajectory, TTC | bbox overlap, deceleration, fall posture |
| Creates an incident? | **Never** | Yes, exactly once per run |
| API fields | `risk_level`, `risk_type`, `collision_probability`, `time_to_collision`, `prediction_active`, `reason` | `incident_confirmed` (alias of the existing `incident_created_this_run`), `last_detection` |
| Frontend | 🟡 amber "PRE-ACCIDENT WARNING" card | 🔴 red "ACCIDENT CONFIRMED" card (always takes priority if both are somehow true) |

`GET /api/ai/status` now returns (additive fields only - nothing
removed):

```json
{
  "running": true,
  "monitoring": true,
  "state": "active",
  "risk_level": "HIGH_RISK",
  "risk_type": "two_wheeler_collision",
  "prediction_active": true,
  "collision_probability": 0.86,
  "time_to_collision": 1.3,
  "reason": "Converging trajectories: projected 62px apart in 1.3s (closing)",
  "risk_track_ids": [12, 18],
  "incident_confirmed": false,
  "incident_created_this_run": false,
  "last_detection": null
}
```

### Testing the accident videos

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/test_risk_predictor.py tests/test_ai_worker.py -v
```

For an end-to-end run against real footage:

1. `AI_MODE=real`, start the backend, open Monitoring, pick a scenario,
   click **START AI MONITORING**.
2. Watch the terminal - you'll see periodic `[AI] Frame N ...` lines,
   and a one-line log every time the risk level *changes*
   (`[AI] Risk -> HIGH_RISK (two_wheeler_collision) prob=0.86 TTC=1.3s ...`),
   followed later by `[AI] ACCIDENT CONFIRMED` / `[AI] Creating incident...`
   if/when Stage 2 confirms.
3. Watch the HUD: it should show the 🟡 amber warning card before
   impact (if the footage gives the tracker enough approach time to
   detect), then switch to the 🔴 red confirmed card afterward.
4. Confirm exactly one incident appears in Dashboard/Incidents per run.

If a video's accident happens too abruptly (e.g. objects already
overlapping in the first frame they're both tracked), there may be too
little runway for a warning to fire before confirmation - this is an
honest limitation of frame-rate/footage, not something to fake around.

---

```
backend/
├── ai_config.py                    central .env-driven AI configuration
├── routes/ai.py                    /api/ai/start /stop /status /stream /detect
└── services/
    ├── detection_service.py        YOLO model loading + inference (rewritten)
    ├── tracking_service.py         per-object movement history (ByteTrack)
    ├── event_analyzer.py           temporal rule-based event detection
    ├── severity_service.py         severity + confidence calculation
    ├── camera_service.py           webcam / video-file abstraction
    └── ai_worker.py                background thread orchestrating it all
```

Nothing in `main.py`, `models.py`, `database.py`, `schemas.py`, or the
existing routes (`incidents.py`, `analytics.py`, `detection.py`) was
removed or had its behavior changed - the real pipeline is additive.

---

## 3. API

| Endpoint | Purpose |
|---|---|
| `POST /api/demo/detection` | **Unchanged.** Canned scenario demo (safety fallback). Not called at all for the "Normal Traffic" scenario - see section 4. |
| `POST /api/ai/start?video_source=...&camera_id=...` | Starts the real AI worker. `video_source` is a path relative to `backend/` (e.g. `sample_video/car_accident.mp4`) - the frontend always passes the path matching whatever video is on screen, so the visible feed and the AI pipeline are guaranteed to be the same file. Returns immediately: `{"status": "started", "camera_id": "CAM-01"}` |
| `POST /api/ai/stop` | Stops the worker. |
| `GET /api/ai/status` | `{ running, state, ai_mode, camera_id, video_source, frames_processed, fps, objects_tracked, last_detection, last_detection_time, incident_created_this_run, device, model, tracker, model_ready, model_load_error, start_error }`. `state` is `"idle" \| "starting" \| "active" \| "error"` and drives the "AI MONITORING: ..." HUD text. |
| `GET /api/ai/detections` | `{ running, detections: [{track_id, class_name, confidence, bbox}], frame_width, frame_height }` - real, per-frame YOLO+ByteTrack output, polled by the Monitoring panel every ~400ms to draw live bounding boxes on top of the video. |
| `GET /api/ai/stream` | MJPEG preview with bounding boxes, track IDs, class names, confidence (server-side rendered alternative to the client-side overlay above). 409 if the worker isn't running. |
| `POST /api/ai/detect` | One-shot YOLO detection on an uploaded image (no tracking history across calls, no incident creation - useful for smoke-testing the model). |

The Monitoring tab now has **exactly one AI control**: a single
"START AI MONITORING" / "STOP AI MONITORING" button, with a merged HUD
(status, model/tracker, FPS, object count, and the confirmed-event
result) drawn directly on the CCTV video panel. There is no longer a
second, separate "Real AI Monitoring" card - see section 4 below.

---

## 4. The Monitoring tab: one integrated AI panel

**Before:** a "Run AI Detection"/"Reset" pair drove a canned demo
pipeline, and a second, separate "Real AI Monitoring" card (visible
only in `AI_MODE=real`) had its own "Start Real AI Monitoring"/"Stop"
buttons. Two AI sections, two sets of controls.

**Now:** one video panel, one HUD, one button.

- **`AI_MODE=demo`**: the button runs/cancels the existing canned
  Detected → Verified → Alerted → Responding pipeline (unchanged
  backend calls). The HUD shows `AI MONITORING: ACTIVE`, `FPS: —`,
  `OBJECTS: —` (no real numbers are invented), and once the pipeline
  reaches "Alerted" it shows the scenario's result text (e.g.
  `ACCIDENT DETECTED`). Selecting **Normal Traffic** in demo mode is a
  pure no-op - it never calls `/api/demo/detection` at all, so it can
  never create an incident, and the HUD eventually shows `NO INCIDENT`.
- **`AI_MODE=real`**: the button calls `POST /api/ai/start` with the
  selected scenario's video, then polls `GET /api/ai/status` and
  `GET /api/ai/detections` to drive the HUD (`AI MONITORING: STARTING`
  → `ACTIVE`, real FPS/object counts) and to draw live, moving
  bounding boxes (real track IDs, class names, YOLO confidence) on top
  of the video. If model loading or the video source fails, the HUD
  shows `AI MONITORING: ERROR` plus the underlying error text.

Switching scenarios always stops whatever's currently running first
(demo or real) so the visible video and the AI worker's source can
never point at two different clips - see the `scenarioId` effect in
`App.jsx`.

---

## 5. Supported detections

| Scenario | Video | category | label | Rule-based signal |
|---|---|---|---|---|
| Vehicle Collision | `car_accident.mp4` | accident | Vehicle Collision | Two vehicle boxes overlap (IoU) + one shows sudden deceleration, or very high overlap alone |
| Two-Wheeler Accident | `two_wheeler_accident.mp4` | accident | Two-Wheeler Accident | Motorcycle/bicycle stops abruptly after moving, or overlaps another object |
| Women Safety Incident | `women_safety.mp4` | safety | Women Safety Incident / Person Distress | A person's box goes from "standing" (tall/narrow) to "lying" (wide/short) and stays that way, OR two people stay close together moving in the same direction for a sustained duration (pursuit-like pattern) |
| Normal Traffic | `normal.mp4` | - | *(no incident)* | Ordinary cars/motorcycles/buses/pedestrians are detected and tracked (visible as bounding boxes) but never satisfy any event rule, so no incident is created |

Every rule requires **temporal confirmation** across
`EVENT_CONFIRM_FRAMES` consecutive frames (default 5) before it can
create an incident - a single noisy frame never triggers anything.
This is also what keeps Normal Traffic safe: ordinary, non-overlapping,
non-decelerating traffic simply never satisfies any rule for 5 frames
running.

---

## 6. Duplicate-incident prevention (one video = one alert)

Two layers, both in `AIWorker`:

1. **Per-run gate (primary rule for the demo)** -
   `self._incident_created_this_run`, a single flag reset to `False`
   every time `POST /api/ai/start` is called. The very first confirmed
   event in a run creates ONE incident and flips this flag to `True`;
   every subsequent confirmed event in the *same* run (even the same
   event type re-detected hundreds of frames later) is silently
   skipped in `AIWorker._process_frame`. Selecting a new scenario/video
   always triggers a fresh `start()` (see section 4), which resets the
   gate - so each video run gets its own single incident.
2. **Cooldown (secondary safeguard)** - `EVENT_COOLDOWN_SECONDS`
   (default 30): the same `(camera_id, event_type)` pair also won't
   re-fire within the cooldown window. This matters if the worker is
   later pointed at a long-running live camera feed instead of a short
   demo clip, where the per-run gate would otherwise be too strict
   (you'd want a *new* incident for a second, distinct accident hours
   later on the same camera).

Both are reset together on every `start()` call.

---

## 7. Configuration (`backend/.env`)

Copy `backend/.env.example` to `backend/.env` and adjust:

```env
AI_MODE=demo                 # "demo" (safe fallback) or "real" (YOLO + ByteTrack)

YOLO_MODEL=yolo11n.pt
CONFIDENCE_THRESHOLD=0.40
TRACKER_CONFIG=bytetrack.yaml
TRACK_HISTORY_LENGTH=60
EVENT_CONFIRM_FRAMES=5
EVENT_COOLDOWN_SECONDS=30

VIDEO_SOURCE=sample_video/car_accident.mp4   # 0 = webcam, or a path under backend/
CAMERA_ID=CAM-01
CAMERA_LOCATION=Anna Salai & Mount Road
CAMERA_X=65
CAMERA_Y=42

AI_TARGET_FPS=12
AI_LOG_EVERY_N_FRAMES=150
```

`VIDEO_SOURCE`/`CAMERA_ID` above are only the *defaults* used if the
frontend ever calls `POST /api/ai/start` with no query params. In
normal use, the Monitoring panel always passes `video_source` and
`camera_id` explicitly for whichever scenario is selected, so the
`.env` values mainly matter for testing the pipeline directly via
`curl` or `/docs`.

No cloud infrastructure, GPS, or real CCTV camera is required. GPU
(CUDA) is used automatically if available (`GET /api/ai/status` ->
`device`), otherwise the pipeline runs on CPU without any extra setup.

---

## 8. Installation

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows — use `source venv/bin/activate` on Mac/Linux
pip install -r requirements.txt
cp .env.example .env         # or manually create .env - see section 6
uvicorn main:app --reload
```

The first time `AI_MODE=real` is used (or `POST /api/ai/start` is
called), Ultralytics downloads `yolo11n.pt` automatically (~6MB) if it
isn't already cached locally - this needs one working internet
connection before the demo, not during it.

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`, backend at
`http://localhost:8000` (Swagger docs at `/docs`).

---

## 9. Activating real AI detection - step by step

1. **Add your 4 demo videos** under `backend/sample_video/`:
   ```
   backend/sample_video/
   ├── car_accident.mp4
   ├── two_wheeler_accident.mp4
   ├── women_safety.mp4
   └── normal.mp4
   ```
   You can start with just one (e.g. `car_accident.mp4`) - the other
   scenario cards will simply show `CCTV VIDEO UNAVAILABLE` until their
   files are added; nothing else breaks.
2. **Set `AI_MODE=real`** in `backend/.env` (see section 6).
3. **Start the backend and frontend** as in section 7.
4. Open the **Monitoring** tab. Pick a scenario card (e.g. "Vehicle
   Collision") - the CCTV panel plays `car_accident.mp4`.
5. Click the single **START AI MONITORING** button. This calls
   `POST /api/ai/start?video_source=sample_video/car_accident.mp4&camera_id=CAM-04`
   - the exact same file the panel is already playing.
6. The HUD in the video panel updates live: `AI MONITORING: STARTING`
   → `ACTIVE`, real `FPS`/`OBJECTS` counts, and moving bounding boxes
   with real YOLO class names, ByteTrack IDs, and confidence values.
7. When the event analyzer confirms an event (collision, two-wheeler
   fall, or a distress/pursuit pattern), the HUD shows the result
   (e.g. `ACCIDENT DETECTED`) and **exactly one** incident appears in
   **Dashboard**, **Incidents**, **Incident Map**, and **Analytics**
   with status `Detected`.
8. Click **STOP AI MONITORING**, or simply pick a different scenario
   card - either stops the worker and resets the per-run dedup gate
   for the next video.
9. **If anything goes wrong on stage** (model didn't download, no
   webcam, laptop overheating): set `AI_MODE=demo` in `.env` and
   restart the backend - the button becomes the canned scenario
   pipeline instead, which always works.

Optional: `GET /api/ai/stream` returns an MJPEG preview with bounding
boxes/track IDs/labels if you want to show the raw detection view in
a browser tab or `<img>` alongside the dashboard.

---

## 10. Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

Covers: model loading (success + failure), detection output structure,
event confidence-threshold behavior, the per-run duplicate-incident
gate (including "cooldown expired but same run" and "new run resets
the gate"), live-detections output shape, severity classification,
camera source configuration, AI start/stop/state lifecycle, and API
response shape - including an end-to-end check that
`POST /api/demo/detection` still flows through to `GET /api/incidents`
unchanged (backward compatibility).

`tests/test_detection_service.py`, `tests/test_ai_worker.py`, and
`tests/test_api_ai_routes.py` mock Ultralytics/the camera so they run
without a GPU, webcam, or downloaded model file.

---

## 11. Fixing a black video feed (postmortem)

If the Monitoring panel ever goes black while `AI MONITORING: ACTIVE`
and real FPS/object numbers are showing, here's what that means and
how it's handled now.

### Root cause

Two separate bugs, both in the streaming *infrastructure* around the
prediction feature, not the prediction math itself:

1. **`GET /api/ai/stream` had no readiness signal and busy-spun with
   no sleep** while waiting for the first frame:
   ```python
   while ai_worker.running:
       frame_bytes = ai_worker.latest_jpeg()
       if frame_bytes is None:
           continue   # tight spin, no backoff, no timeout
   ```
2. **The frontend swapped from the plain `<video>` to the live
   `<img src=".../stream">` the instant `aiStatus.running` became
   `true`** - which happens as soon as the worker *thread starts*,
   well before YOLO's first (CPU warm-up) inference has actually
   produced and encoded a frame, often several seconds later. The
   `<img>` latched onto an empty stream during that gap and, on some
   browsers, never recovered even once frames started arriving - a
   known fragility of MJPEG-via-`<img>`.

Together: the AI worker thread starts -> HUD immediately shows real
FPS/objects (the loop genuinely is running) -> but the `<img>` already
latched onto nothing during warm-up. Exactly the symptom reported.

### The fix

| File | Change |
|---|---|
| `backend/services/ai_worker.py` | Added `self._stream_ready`, set `True` only once `_render_preview()` has actually encoded and stored a real JPEG (not just because the worker is running). Reset on every `start()`. Exposed via `status()`. Added `[VIDEO]`/`[AI]`/`[STREAM]` debug logging. |
| `backend/services/camera_service.py` | Added the requested `[VIDEO] Source / Absolute path / Exists / Capture opened / FPS / Width / Height` logging in both `WebcamSource.open()` and `VideoFileSource.open()`. |
| `backend/routes/ai.py` | Replaced the busy-spin in `ai_stream()`'s generator with a paced loop (`time.sleep(0.03)` between polls) and a bounded 15s startup timeout that closes the stream cleanly (rather than spinning forever) if no frame ever arrives. Added `[STREAM]` connection-lifecycle logging. |
| `frontend/src/App.jsx` | The `<img>` now only swaps in once `aiStatus.stream_ready` is `true` - not just `running`. Added a "CONNECTING TO AI ANALYSIS..." badge over the still-playing plain video during warm-up, and an "AI STREAM UNAVAILABLE - Showing original CCTV feed" badge (18s client-side timeout, or the `<img>`'s own `onError`) so the panel can never go black. The `<img>`'s `key` is now the video source captured once when the run started (`aiRunVideoSource`), not the polled status object, removing any risk of an unnecessary remount interrupting the stream mid-run. |
| `backend/tests/test_ai_worker.py` | Added `test_stream_becomes_ready_only_after_a_real_frame_is_rendered` and `test_stream_ready_resets_on_a_new_start`, which reproduce the exact bug directly against the real (unmocked) `_render_preview()` code path. Extended `test_status_shape`. |

Nothing about the pre-accident prediction pipeline (`risk_predictor.py`,
`event_analyzer.py`, incident creation, dedup) was touched.

### What the panel does now

```
Click START AI MONITORING
        |
        v
Plain video keeps playing (unchanged)
        |
        v
Worker starts -> aiStatus.running = true, stream_ready = false
        |
        v
"CONNECTING TO AI ANALYSIS..." badge shown over the still-playing video
        |
        v
First frame encoded -> stream_ready = true
        |                                   \
        v                                    v (never happens / timeout)
Swap to live MJPEG stream              "AI STREAM UNAVAILABLE" badge,
(YOLO boxes, track IDs, HUD)           keep showing the plain video
```

---

## 12. Limitations - please read before demoing

- This is a hackathon prototype, not a certified safety system. It
  **cannot reliably detect every real-world accident or crime.**
- Event rules (collision/fall/pursuit) are heuristics tuned for
  clarity and explainability, not a trained classifier - expect false
  positives/negatives on footage very different from what they were
  tuned against. In particular, "Normal Traffic" only stays
  incident-free if the footage genuinely doesn't produce overlapping/
  decelerating/falling-looking motion - a chaotic or low-quality clip
  could still trip a rule.
- **Bounding-box scaling is an approximation.** The live overlay maps
  YOLO's pixel coordinates onto the displayed `<video>` element as
  simple percentages of frame width/height. This lines up well when
  the source video's aspect ratio is close to the panel's 16:9, but
  will drift slightly for very different aspect ratios because
  `object-fit: cover` crops the video before the percentage math is
  applied. Good enough for a live demo overlay, not pixel-perfect.
- A single camera worker runs at a time in this build (`ai_worker.py`
  is a singleton) - multi-camera support is a natural next step given
  the `CameraSource` abstraction, but isn't wired up yet.
- **One incident per video run is intentional and absolute** - even a
  genuinely different second accident later in the same clip will NOT
  create a second incident until the worker is stopped/restarted. This
  matches the demo requirement exactly; a production deployment
  watching a continuous live feed would want a different policy here.
- Location (`x`, `y`, `location`) comes from configured camera
  metadata, not GPS - a normal video feed has no coordinates.
- `GET /api/ai/stream` is best-effort MJPEG, not a production video
  protocol.

---

## Notes carried over from the original project

- CORS is preconfigured on the backend for `localhost:5173`. If Vite
  picks a different port, add it to `CORS_ORIGINS` in `backend/.env`.
- The backend keeps an incident's *real* severity forever and exposes
  a `display_severity` field that becomes `"resolved"` once an
  incident reaches that status - this is what the frontend uses for
  badge colors.
