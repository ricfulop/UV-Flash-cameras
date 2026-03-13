# Flash Reactor Dual-Camera Imaging System — Project Specification

## Overview

Build a Python application for simultaneous acquisition, live preview, and recording from two USB3 UV-sensitive cameras (Sony IMX478 sensor, 200 nm–Vis, 8 MP) used in a plasma flash reduction reactor. The cameras have **different SDKs** and **different optical configurations**, and the software must handle both seamlessly within a unified interface.

> **Target environment:** Desktop Python app (Windows primary, macOS secondary). Cursor IDE / VS Code development.

---

## Hardware Summary

### Camera 1 — Allied Vision (Wide-Field / Overview)

| Parameter | Value |
|---|---|
| **Sensor** | Sony IMX478, 8 MP, UV-enhanced (200 nm – Vis) |
| **Interface** | USB 3.0 |
| **SDK** | Vimba X (Allied Vision) |
| **Lens** | 78 mm f/3.8 |
| **Working distance** | 600 mm (60 cm) |
| **Field of view** | 52 × 52 mm |
| **Role** | Overview imaging of the flash event / reactor cross-section |

### Camera 2 — Basler (Close-Up / Filtered)

| Parameter | Value |
|---|---|
| **Sensor** | Sony IMX478, 8 MP, UV-enhanced (200 nm – Vis) |
| **Interface** | USB 3.0 |
| **SDK** | Basler Pylon |
| **Lens** | 25 mm f/2.8 |
| **Working distance** | 20 mm |
| **Field of view** | 54 × 54 mm |
| **Front-mounted filter wheel** | Manually swapped filters (see below) |
| **Role** | Close-up / spectrally-filtered imaging of wire surface and near-plasma region |

#### Basler Filter Set

| Filter | Passband | Purpose |
|---|---|---|
| **UV shortpass** | ≤ 400 nm | Isolate UV emission from flash event |
| **Ar I narrow-band** | 810 nm ± 5 nm (10 nm FWHM) | Monitor neutral argon emission (Ar I 811.5 nm line) |
| **Ar II / OH narrow-band** | 780 nm ± 5 nm (10 nm FWHM) | Monitor 780 nm region (Ar I 772.4 nm, nearby Ar II, or OH emission depending on plasma chemistry) |

> The filter is changed manually between runs. The software must let the operator **log which filter is currently installed** as metadata attached to each recording session.

---

## Software Architecture

### Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.10+ | Both SDKs have mature Python bindings |
| **GUI framework** | PyQt6 or PySide6 | Hardware-accelerated rendering, mature ecosystem |
| **IPC** | ZeroMQ (pyzmq) | PUB/SUB bus between camera app and OES Flash Plasma app (also PyQt6) |
| **Allied Vision SDK** | VmbPy (Vimba X Python API) | Official Python wrapper for Vimba X |
| **Basler SDK** | pypylon | Official Pylon Python wrapper |
| **Image pipeline** | NumPy / OpenCV | Frame conversion, display scaling, overlays |
| **Recording format** | TIFF stack (lossless, live) + H.265 MP4 (preview, post-acquisition) | TIFF preserves 16-bit/raw data; H.265 for quick review |
| **Metadata** | JSON sidecar per session | Camera params, filter, timestamps, user notes |
| **Config** | YAML | Persistent camera settings and app preferences |

### Module Structure

```
flash-camera/
├── main.py                     # Entry point, app init
├── config/
│   ├── default_config.yaml     # Default settings
│   └── camera_presets.yaml     # Per-camera saved presets
├── core/
│   ├── camera_manager.py       # Abstract camera interface + discovery
│   ├── allied_vision_camera.py # VmbPy wrapper implementing CameraInterface
│   ├── basler_camera.py        # pypylon wrapper implementing CameraInterface
│   ├── frame_buffer.py         # Thread-safe ring buffer for frames (2s pre-trigger)
│   ├── recorder.py             # Recording engine (TIFF stack + H.265 encode)
│   ├── quality_presets.py      # Preset definitions and TIFF writer config
│   └── ipc_bus.py              # ZeroMQ PUB/SUB bus (OES ↔ Camera app)
├── gui/
│   ├── main_window.py          # Top-level layout with dual viewports
│   ├── camera_panel.py         # Per-camera controls widget
│   ├── live_view.py            # OpenGL or QImage-based live display
│   ├── recording_controls.py   # Start/stop, filename, session metadata
│   ├── quality_selector.py     # Recording quality preset radio buttons + custom mode
│   ├── filter_selector.py      # Basler filter logging widget
│   ├── histogram_widget.py     # Live intensity histogram per camera
│   └── overlay_controls.py     # Scale bars, crosshairs, ROI
├── utils/
│   ├── timestamp.py            # Synchronized timestamps across cameras
│   ├── metadata.py             # JSON sidecar read/write
│   └── image_utils.py          # Bit-depth conversion, debayer, LUT
└── tests/
    ├── test_camera_interface.py
    └── test_recorder.py
```

### Project Configuration (`pyproject.toml`)

```toml
[project]
name = "flash-camera"
version = "0.1.0"
requires-python = ">=3.10"
description = "Dual-camera imaging system for General Flash plasma reactor"
dependencies = [
    "PyQt6>=6.5",
    "pyzmq>=25.0",
    "pypylon>=3.0",
    "VmbPy>=1.0",
    "numpy>=1.24",
    "opencv-python-headless>=4.8",
    "tifffile>=2023.7",
    "Pillow>=10.0",
    "PyYAML>=6.0",
    "ffmpeg-python>=0.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-qt>=4.2",
    "ruff>=0.1",
]

[project.scripts]
flash-camera = "flash_camera.main:main"
export-session = "flash_camera.utils.export_session:main"
```

> **Note:** `VmbPy` and `pypylon` require their respective native SDKs (Vimba X, Pylon) to be installed first. The pip packages are Python bindings only. `ffmpeg-python` requires `ffmpeg` on the system PATH for H.265 encoding.

### Default Configuration (`config/default_config.yaml`)

```yaml
# ── Camera Identity ──────────────────────────────────────────────
# Set these to your actual serial numbers so the app auto-assigns
# cameras on startup regardless of USB enumeration order.
cameras:
  allied_vision:
    serial: "ALLIED_VISION_SERIAL_HERE"   # ← Replace with actual serial
    role: overview
    default_pixel_format: Mono12          # Mono8 for alignment, Mono12 for data
    default_exposure_us: 500
    default_gain_db: 0.0
    lens: "78mm f/3.8"
    working_distance_mm: 600
    fov_mm: [52, 52]
  basler:
    serial: "BASLER_SERIAL_HERE"          # ← Replace with actual serial
    role: closeup_filtered
    default_pixel_format: Mono12
    default_exposure_us: 200
    default_gain_db: 0.0
    default_filter: "no_filter"           # Options: uv_shortpass, 810nm_ArI, 780nm, no_filter
    lens: "25mm f/2.8"
    working_distance_mm: 20
    fov_mm: [54, 54]

# ── Recording ────────────────────────────────────────────────────
recording:
  data_root: "D:/flash_data"              # Shared root for camera + OES data
  session_naming: "{date}_{time}_{name}"  # e.g., 20260312_143022_flash_run_047
  pretrigger_buffer_s: 2.0
  default_quality_preset: "high"          # maximum, high, balanced, fast, compact, custom
  tiff_format: single_files               # "single_files" (one TIFF per frame) or "stack" (multi-page)
  h265_crf: 20                            # CRF for preview encode (18=high quality, 22=smaller files)
  h265_downscale: 1080                    # Preview video height in pixels

  # Custom preset overrides (only used when default_quality_preset is "custom")
  custom_quality:
    bit_depth: Mono12                     # Mono8 or Mono12
    max_fps: 30                           # 0 = sensor max
    tiff_compression: lzw                 # none, lzw, zstd

# ── ZeroMQ IPC ───────────────────────────────────────────────────
zmq:
  oes_pub_port: 5555                      # OES app publishes commands here
  camera_pub_port: 5556                   # Camera app publishes status here
  heartbeat_interval_s: 1.0

# ── Display ──────────────────────────────────────────────────────
display:
  target_fps: 15                          # GUI refresh rate (independent of acquisition)
  default_colormap: gray                  # gray, inferno, viridis, plasma
  show_crosshair: true
  show_scale_bar: true
  show_histogram: true
```

### Session Data Directory Convention

All session data lives under a shared root (`data_root` in config, default `D:/flash_data`). Both the camera app and OES Flash Plasma app write to this root so cross-references resolve without path mapping.

```
D:/flash_data/
├── 2026-03-12/
│   ├── 20260312_143022_flash_run_047/
│   │   ├── metadata.json                    # Camera session metadata (FR-4)
│   │   ├── allied_vision/
│   │   │   ├── frame_000000.tif             # Individual 12-bit TIFFs
│   │   │   ├── frame_000001.tif
│   │   │   ├── ...
│   │   │   └── preview.mp4                  # H.265 preview (generated post-session)
│   │   └── basler/
│   │       ├── frame_000000.tif
│   │       ├── frame_000001.tif
│   │       ├── ...
│   │       └── preview.mp4
│   ├── 20260312_143022_flash_run_047.oes.h5 # OES spectrometer data (written by OES app)
│   └── ...
└── 2026-03-13/
    └── ...
```

- Date directories are created automatically.
- Session subdirectory name matches the `session_id` in metadata.
- OES `.h5` files sit alongside the camera session directory at the same level, linked by `session_id`.
- The camera app creates the session directory on record start; the OES app references it via the ZMQ `session_id`.

---

## GUI Layout

### Wireframe

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Flash Camera   [● OES Connected]          [⏺ REC 00:12.4]   [■ Stop]         │
├────────────────────────────────┬────────────────────────────────────────────────┤
│                                │                                                │
│   Allied Vision (Overview)     │   Basler (Close-Up)                            │
│   ┌──────────────────────┐     │   ┌──────────────────────┐                     │
│   │                      │     │   │                      │                     │
│   │                      │     │   │                      │                     │
│   │    Live View         │     │   │    Live View         │                     │
│   │    (zoom/pan)        │     │   │    (zoom/pan)        │                     │
│   │         +            │     │   │         +            │                     │
│   │                      │     │   │                      │                     │
│   │                      │     │   │                      │                     │
│   │  ├──┤ 10mm           │     │   │  ├──┤ 10mm           │                     │
│   │  30.0 fps  Mono12    │     │   │  30.0 fps  Mono12    │                     │
│   └──────────────────────┘     │   └──────────────────────┘                     │
│   ┌──────────────────────┐     │   ┌──────────────────────┐  ┌───────────────┐  │
│   │ ▁▂▃▅▇▅▃▂▁  Histogram │     │   │ ▁▂▃▅▇▅▃▂▁  Histogram│  │ FILTER:       │  │
│   └──────────────────────┘     │   └──────────────────────┘  │ ○ No filter   │  │
│                                │                              │ ○ UV ≤400nm   │  │
│   Exposure ──●────── 500 µs    │   Exposure ──●────── 200 µs │ ● 810nm ArI   │  │
│   Gain     ──●──────   0 dB    │   Gain     ──●──────   0 dB │ ○ 780nm       │  │
│   Format   [Mono12      ▾]    │   Format   [Mono12      ▾] └───────────────┘  │
│   ROI      [Full frame    ]    │   ROI      [Full frame    ]                    │
│                                │                                                │
├────────────────────────────────┴────────────────────────────────────────────────┤
│  Quality: [● Max ○ High ○ Balanced ○ Fast ○ Compact ○ Custom]  ~43 GB/min     │
│  Session: flash_run_047  │  Notes: [Ar/H2 mix, 50V, 200 mTorr          ]      │
│  ● AV: 373 frames  ● Basler: 373 frames  │  [H.265 encode: ████░░ 68%]        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Layout Rules

- **Top bar:** App title, OES connection indicator (green dot = connected, red = no heartbeat in >3s), recording state with elapsed time, stop button.
- **Center:** Resizable QSplitter dividing two camera viewports. Each viewport has its own live view with overlay (crosshair, scale bar, fps/format label), histogram below the image, and camera controls (exposure slider, gain slider, pixel format dropdown, ROI).
- **Basler panel only:** Filter selector radio buttons to the right of the Basler histogram. Colored highlight on the selected filter. The filter label also appears as an overlay in the Basler live view corner.
- **Bottom bar:** Quality preset radio buttons with live estimated storage rate (updates when preset changes or when recording to show actual rate). Current session name, editable notes field (pre-populated from OES app if triggered via ZMQ), per-camera frame counters, H.265 encoding progress for any background jobs. Quality preset is **locked during recording** — greyed out with a lock icon. Changing preset while not recording immediately updates the pixel format on both cameras (visible in the viewport overlays).
- **Dark theme:** All backgrounds dark gray (#1e1e1e), text light gray (#cccccc), accent color for recording state (red pulse when recording). Use `QPalette` dark theme or `qdarkstyle`.

---

## Error Handling Policy

### During Recording

| Failure | Behavior | User Notification |
|---|---|---|
| **Single camera drops frames** | Continue recording both cameras. Log dropped frame indices in metadata. Insert blank/duplicate frame in TIFF sequence to maintain frame-count alignment. | Yellow warning icon + "AV: 3 frames dropped" counter on the affected viewport. |
| **Single camera disconnects** | Continue recording the remaining camera. Mark the disconnected camera's stream as interrupted in metadata with the disconnect timestamp. | Red "DISCONNECTED" overlay on affected viewport. Audio beep. |
| **Both cameras disconnect** | Stop recording. Flush all buffered frames to disk. Save partial metadata. | Full-screen red alert: "Both cameras lost. Session saved (partial)." |
| **Disk write falls behind** | If the TIFF writer queue exceeds 200 frames (~6.7s at 30fps), drop the oldest un-written frames and log the gap. Never block the acquisition thread. | Orange "WRITE LAG: 45 frames behind" warning in bottom bar. |
| **Disk full** | Stop recording immediately. Flush what's possible. Save metadata. | Red alert: "Disk full. Recording stopped. X frames saved." |
| **OES app disconnects mid-recording** | Continue camera recording normally. The camera app is fully independent once recording has started. | OES indicator turns red. Session metadata notes "oes_disconnected_during_recording: true". |

### Outside Recording

| Failure | Behavior |
|---|---|
| **Camera not found on startup** | Show camera slot as "Not connected" with a "Rescan" button. App launches in single-camera or no-camera mode. |
| **SDK initialization failure** | Log the full traceback. Display a diagnostic message suggesting: check USB cable, check SDK installation, check if another app holds the camera. |
| **Config file missing/corrupt** | Fall back to hardcoded defaults. Log a warning. Recreate `default_config.yaml` on next save. |
| **H.265 encode fails** | Log the error. Retain the raw TIFF stack (which is the primary data anyway). Offer "Retry encode" button. |

### General Principles

- **Never lose frames silently.** Every dropped, skipped, or failed frame must be logged in the session metadata with its index and timestamp.
- **Never block acquisition.** The frame capture thread has the highest priority. Display, recording, and IPC all run on separate threads and degrade gracefully.
- **Always save something.** Even on a crash, the auto-save writes partial metadata and flushes the TIFF writer queue. On next launch, detect incomplete sessions and offer recovery.

---

## Camera Abstraction Layer

Both cameras must implement a common `CameraInterface` so the GUI and recording engine are SDK-agnostic.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np

@dataclass
class FrameMetadata:
    timestamp_ns: int           # Camera hardware timestamp (nanoseconds)
    frame_id: int               # Sequential frame counter
    exposure_us: float          # Actual exposure for this frame (microseconds)
    gain_db: float              # Actual gain for this frame (dB)
    camera_id: str              # "allied_vision" or "basler"
    pixel_format: str           # e.g., "Mono8", "Mono12", "BayerRG8"

class CameraInterface(ABC):

    @abstractmethod
    def open(self) -> None:
        """Connect to camera, allocate buffers."""

    @abstractmethod
    def close(self) -> None:
        """Release resources."""

    @abstractmethod
    def start_acquisition(self) -> None:
        """Begin continuous frame streaming."""

    @abstractmethod
    def stop_acquisition(self) -> None:
        """Stop streaming."""

    @abstractmethod
    def get_frame(self, timeout_ms: int = 1000) -> tuple[np.ndarray, FrameMetadata]:
        """Return (image_array, metadata). Blocks up to timeout."""

    @abstractmethod
    def set_exposure(self, us: float) -> None:
        """Set exposure time in microseconds."""

    @abstractmethod
    def set_gain(self, db: float) -> None:
        """Set analog gain in dB."""

    @abstractmethod
    def get_exposure_range(self) -> tuple[float, float]:
        """Return (min_us, max_us)."""

    @abstractmethod
    def get_gain_range(self) -> tuple[float, float]:
        """Return (min_db, max_db)."""

    @abstractmethod
    def set_pixel_format(self, fmt: str) -> None:
        """Set pixel format (e.g., Mono8, Mono12, Mono16, BayerRG8)."""

    @abstractmethod
    def get_pixel_formats(self) -> list[str]:
        """Return available pixel formats."""

    @abstractmethod
    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        """Set region of interest (sensor crop). Set all to 0 for full frame."""

    @abstractmethod
    def get_sensor_size(self) -> tuple[int, int]:
        """Return (width, height) in pixels."""

    @abstractmethod
    def get_camera_info(self) -> dict:
        """Return dict with model, serial, firmware, SDK version."""

    @abstractmethod
    def set_trigger_mode(self, mode: str) -> None:
        """Set trigger: 'freerun', 'software', 'hardware_rising', 'hardware_falling'."""

    @abstractmethod
    def get_frame_rate(self) -> float:
        """Return current/actual frame rate in fps."""
```

---

## Key Functional Requirements

### FR-1: Camera Discovery and Initialization

- On launch, enumerate USB3 devices using both Vimba X and Pylon transport layers.
- Auto-identify each camera by serial number (stored in config) so assignments are persistent even if USB enumeration order changes.
- Display connection status for each camera in the GUI. Allow manual re-scan.
- Gracefully handle one camera being absent (single-camera mode).

### FR-2: Dual Live View

- Display both camera feeds simultaneously in a side-by-side layout (resizable splitter).
- Target ≥ 15 fps display refresh for each camera (decouple display rate from acquisition rate).
- Support independent zoom/pan per viewport.
- Overlay options per viewport: crosshair, scale bar (calibrated from FOV), ROI rectangle, intensity colormap (false color for 12/16-bit).
- Display real-time info overlay: fps, exposure, gain, frame counter, timestamp, and (for Basler) current filter.

### FR-3: Camera Controls

Per camera, expose:
- **Exposure time** — slider + numeric entry (µs), with range from camera.
- **Gain** — slider + numeric entry (dB).
- **Pixel format** — dropdown (Mono8, Mono12, Mono16, BayerRG8, etc. as available).
- **ROI** — draw on live view or enter numerically (x, y, w, h). Full-frame reset button.
- **Frame rate** — display actual achieved rate; allow max rate or capped rate.
- **Trigger mode** — freerun (default) or software trigger (from GUI button, keyboard shortcut, or ZMQ command from OES app).
- **Auto-exposure** — toggle (useful for alignment, disabled during recording).
- **White balance / Flat-field correction** — load a reference frame, apply per-pixel correction.

### FR-4: Recording

- **Simultaneous recording** from both cameras with a single Start/Stop control.
- **Per-camera recording** also available (record one, preview other).

#### Recording Quality Presets

The operator selects a quality preset before recording. All presets are **lossless** — no lossy compression is ever applied to raw imaging data. The tradeoffs are bit depth, frame rate, and lossless compression overhead.

| Preset | Bit Depth | Max FPS | TIFF Compression | Est. Write Rate (2 cams) | Est. Storage/min | Use Case |
|---|---|---|---|---|---|---|
| **Maximum** | Mono12 | Sensor max (~30) | None | ~720 MB/s | ~43 GB | Quantitative analysis, line-ratio imaging, publication data |
| **High** | Mono12 | Sensor max (~30) | LZW | ~400–550 MB/s* | ~25–33 GB | Default for most flash experiments — full dynamic range, smaller files |
| **Balanced** | Mono12 | 15 fps cap | LZW | ~200–275 MB/s* | ~12–16 GB | Long-duration monitoring, reduced storage pressure |
| **Fast** | Mono8 | Sensor max (~30) | None | ~480 MB/s | ~29 GB | High-speed events where 8-bit dynamic range is sufficient |
| **Compact** | Mono8 | 15 fps cap | LZW | ~100–160 MB/s* | ~6–10 GB | Extended unattended recording, alignment sessions |
| **Custom** | User-set | User-set | User-set | Varies | Varies | Full manual control of all parameters |

*LZW compression ratios depend on image content. Plasma images with large dark regions compress well (40–60% of raw). Bright saturated frames compress poorly.

**Implementation notes:**
- Selecting a preset sets the pixel format on both cameras and configures the TIFF writer. The operator can still override individual camera pixel formats in FR-3, which automatically switches the preset indicator to "Custom."
- The frame rate cap is applied in the recording pipeline (frame decimation), not on the camera sensor. The live view always runs at full sensor rate regardless of preset. This means the pre-trigger buffer always captures at full rate; only the frames written to disk are decimated.
- LZW compression is applied per-frame in the TIFF writer thread. If the compression throughput can't keep up with the frame rate, the writer falls back to uncompressed for that frame and logs a warning. This prevents frame drops.
- The estimated storage rate is displayed live in the bottom status bar during recording so the operator can see actual disk usage.
- The preset is recorded in session metadata so post-processing scripts know the data format.

- **Lossless TIFF stack** as primary format — one multi-page TIFF or numbered single TIFFs per camera. Bit depth and compression determined by the selected quality preset. This is the only format written during active acquisition.
- **H.265 preview video** generated as a background task on session save/close. Encode from the TIFF stack using FFmpeg `libx265` with CRF 18–22 (visually lossless, ~1–5% of raw size). Downscale to 1080p for the preview. This runs post-acquisition so it cannot interfere with frame capture.
  - The encoding job should be queued and non-blocking — the operator can start a new recording while the previous session's preview is still encoding.
  - Display a progress indicator in the GUI for active encoding jobs.
  - If the operator closes the app with encoding jobs pending, warn and offer to finish encoding or cancel.
- **Pre-trigger buffer** — 2-second circular ring buffer per camera, always at full sensor rate and native bit depth regardless of recording preset. When recording starts, the buffer is flushed to disk (applying the preset's compression/decimation), so the TIFF stack includes the 2 seconds leading up to the event. Buffer RAM: ~1.4 GB (Mono12) or ~960 MB (Mono8) for both cameras.
- **Session metadata** (JSON sidecar) auto-generated per recording:

```json
{
  "session_id": "20260312_143022_flash_run_047",
  "operator": "Ric",
  "recording_quality": {
    "preset": "high",
    "bit_depth": "Mono12",
    "max_fps": 30,
    "tiff_compression": "lzw",
    "actual_avg_write_mb_s": 487.3
  },
  "start_time_utc": "2026-03-12T14:30:22.123456Z",
  "duration_s": 12.45,
  "cameras": {
    "allied_vision": {
      "model": "...",
      "serial": "...",
      "exposure_us": 500,
      "gain_db": 6.0,
      "pixel_format": "Mono12",
      "roi": [0, 0, 3840, 2160],
      "frame_count": 373,
      "avg_fps": 29.96,
      "lens": "78mm f/3.8",
      "working_distance_mm": 600,
      "fov_mm": [52, 52]
    },
    "basler": {
      "model": "...",
      "serial": "...",
      "exposure_us": 200,
      "gain_db": 0.0,
      "pixel_format": "Mono12",
      "roi": [0, 0, 3840, 2160],
      "frame_count": 373,
      "avg_fps": 29.96,
      "lens": "25mm f/2.8",
      "working_distance_mm": 20,
      "fov_mm": [54, 54],
      "filter_installed": "810nm_ArI"
    }
  },
  "reactor_conditions": {
    "gas": "",
    "pressure_torr": null,
    "voltage_v": null,
    "current_a": null,
    "notes": ""
  },
  "oes_sync": {
    "oes_session_file": "oes_data/flash_run_047.h5",
    "oes_start_utc": "2026-03-12T14:30:22.123456Z",
    "camera_start_utc": "2026-03-12T14:30:22.124012Z",
    "clock_offset_us": 556,
    "sync_method": "zmq_start_message",
    "triggered_by": "oes_app"
  },
  "file_paths": {
    "allied_vision_tiff": "session_047/av_frames.tif",
    "basler_tiff": "session_047/basler_frames.tif",
    "allied_vision_mp4": "session_047/av_preview.h265.mp4",
    "basler_mp4": "session_047/basler_preview.h265.mp4"
  }
}
```

### FR-5: Filter Logging (Basler Only)

- Dropdown or button group in the Basler camera panel: `UV Shortpass (≤400nm)`, `810nm Ar I`, `780nm`, `No Filter`.
- Selected filter is written into session metadata automatically.
- Optionally display a colored indicator / label on the Basler live view so the operator always knows what filter is active.
- Filter selection persists across app restarts (last known filter loaded from config).

### FR-6: Trigger and IPC with OES Flash Plasma App

Both the camera app and the OES Flash Plasma app are **PyQt6**. Use **ZeroMQ (pyzmq)** for inter-process communication — it's lightweight, handles either app restarting independently, and avoids the overhead of a full WebSocket server.

#### Trigger Sources (either can start/stop recording)

1. **OES Flash Plasma app** — sends a ZMQ message when its own record button is pressed. This is the primary workflow: one button press starts both OES acquisition and camera recording.
2. **Camera app record button / `Space` key** — for standalone operation (alignment, calibration, testing without the OES app running).

Both trigger paths feed into the same recording pipeline. When triggered, both cameras flush their **2-second pre-trigger ring buffer** (see FR-4) into the TIFF stack and continue recording live frames until stop is received.

#### ZeroMQ Bus Architecture

```
┌──────────────────────┐         ZMQ PUB/SUB          ┌──────────────────────┐
│  OES Flash Plasma    │ ──── tcp://localhost:5555 ──→ │  Camera App          │
│  (PyQt6)             │ ←── tcp://localhost:5556 ──── │  (PyQt6)             │
│                      │                               │                      │
│  PUB: commands       │         ZMQ PUB/SUB           │  PUB: status/frames  │
│  SUB: camera status  │                               │  SUB: OES commands   │
└──────────────────────┘                               └──────────────────────┘
```

- **Port 5555** — OES app publishes, camera app subscribes. Topics: `cmd/record/start`, `cmd/record/stop`, `cmd/ping`.
- **Port 5556** — Camera app publishes, OES app subscribes. Topics: `status/recording`, `status/heartbeat`, `data/frame_info`.
- Both ports are configurable in `config/default_config.yaml`.
- PUB/SUB is fire-and-forget — if one app is down, the other continues without blocking. Heartbeat messages (1 Hz) let each app display the other's connection status.

#### Message Format

```python
# All messages are JSON-encoded, prefixed with a topic string.
# OES → Camera:
topic: b"cmd/record/start"
payload: {
    "session_id": "flash_run_047",
    "notes": "Ar/H2 mix, 50V, 200 mTorr",
    "oes_file": "oes_data/flash_run_047.h5",   # path to OES data for cross-reference
    "timestamp_utc": "2026-03-12T14:30:22.123456Z"
}

topic: b"cmd/record/stop"
payload: {
    "session_id": "flash_run_047",
    "timestamp_utc": "2026-03-12T14:30:34.567890Z"
}

# Camera → OES:
topic: b"status/recording"
payload: {
    "state": "started",  # or "stopped"
    "session_id": "flash_run_047",
    "frame_counts": {"allied_vision": 0, "basler": 0},
    "timestamp_utc": "..."
}

topic: b"status/heartbeat"
payload: {
    "cameras_connected": ["allied_vision", "basler"],
    "is_recording": false,
    "buffer_depth_s": 2.0
}
```

- The `session_id` and `oes_file` path from the OES app are written directly into the camera session metadata (FR-4), creating a hard link between the camera and spectrometer datasets.

### FR-7: Timestamp Synchronization and OES Log Sync

- Both cameras run on USB3 with independent clocks. Log each frame's hardware timestamp.
- At session start, record a common system-clock reference (`time.perf_counter_ns()` + UTC wall clock) for both cameras so post-processing can align frames to each other and to OES data.
- **OES synchronization:** The ZMQ `cmd/record/start` message includes a UTC timestamp from the OES app. The camera app logs its own UTC timestamp at the same moment. This gives a common epoch for aligning camera frames to OES spectra in post-processing.
- **Synchronized session log:** During recording, the camera app publishes per-frame summary messages on the ZMQ bus (`data/frame_info` topic) containing frame index, hardware timestamp, and mean intensity. The OES app can subscribe to these and log them alongside spectral data, creating a unified time-series that correlates imaging events with emission spectra.
- The session metadata JSON includes an `oes_sync` block:

```json
"oes_sync": {
    "oes_session_file": "oes_data/flash_run_047.h5",
    "oes_start_utc": "2026-03-12T14:30:22.123456Z",
    "camera_start_utc": "2026-03-12T14:30:22.124012Z",
    "clock_offset_us": 556,
    "sync_method": "zmq_start_message"
}
```

### FR-8: Data Export and Post-Processing Hooks

- Recorded TIFF stacks and metadata should be compatible with ImageJ/FIJI, Python (tifffile), and MATLAB.
- Provide a utility script (`export_session.py`) that reads a session's JSON metadata and can: produce a montage of both cameras side-by-side, extract single frames by index or timestamp, compute frame-to-frame intensity statistics (for flash event detection).

### FR-9: OES Flash Plasma App Modifications (OES-Side Scope)

The following changes are needed in the existing OES Flash Plasma app to enable the integration:

1. **Add ZMQ publisher** to the existing record button handler: on record start, publish `cmd/record/start` with session ID, notes, and OES file path. On record stop, publish `cmd/record/stop`.
2. **Add ZMQ subscriber** (background QThread) to receive `status/recording` and `status/heartbeat` from the camera app.
3. **Connection indicator** in the OES GUI: show green/red dot for camera app connection status (based on heartbeat).
4. **Optional: subscribe to `data/frame_info`** to log per-frame camera intensity alongside OES spectral time-series (enables post-processing correlation of broadband imaging intensity vs. emission line ratios).

---

## Non-Functional Requirements

### NFR-1: Performance

- Sustain full-sensor 8 MP acquisition at ≥ 30 fps per camera simultaneously without dropped frames. Both cameras will be on **separate USB3 host controllers** (confirmed), providing ~5 Gbps usable bandwidth per camera.
- Frame display can run at lower rate (15 fps) with decimation to keep GUI responsive.
- Recording write throughput depends on quality preset: ~720 MB/s peak (Maximum) down to ~100 MB/s (Compact). NVMe SSD required for Maximum and High presets. SATA SSD may suffice for Balanced/Compact. The H.265 preview encode runs post-acquisition as a background job.
- LZW compression runs in the TIFF writer thread. If compression can't keep pace, fall back to uncompressed for individual frames rather than dropping them (see Error Handling Policy).

### NFR-2: Reliability

- Graceful recovery from USB disconnect/reconnect (hot-plug tolerance).
- Watchdog on frame acquisition threads — alert operator if frames are dropped.
- Auto-save session metadata even on unexpected exit (crash recovery).

### NFR-3: Usability

- Single-window layout; no floating dialogs during normal operation.
- Keyboard shortcuts for critical actions: `Space` = start/stop recording, `T` = software trigger, `F` = toggle fullscreen on selected camera, `1/2` = select camera, `Q` = cycle quality preset (disabled during recording).
- Dark theme (reduce ambient light interference in lab).

### NFR-4: Extensibility

- The `CameraInterface` abstraction allows adding future cameras (e.g., FLIR/Teledyne) without modifying GUI or recording code.
- Plugin architecture for post-processing: register Python callables that receive each frame during or after acquisition (e.g., real-time intensity thresholding for flash detection).

---

## SDK and Dependency Installation Notes

### ZeroMQ (IPC Bus)

```bash
pip install pyzmq
# Verify:
python -c "import zmq; print(zmq.zmq_version())"
```

- Used for PUB/SUB communication between camera app and OES Flash Plasma app.
- Both apps must agree on port numbers (default: 5555 OES→Camera, 5556 Camera→OES).

### Allied Vision — Vimba X

```bash
# Install Vimba X SDK from Allied Vision website (includes USB transport layer)
# Then install Python bindings:
pip install VmbPy
# Verify:
python -c "import vmbpy; print(vmbpy.__version__)"
```

- Vimba X replaces the older Vimba SDK. Use `VmbPy`, not `pymba`.
- On macOS, Allied Vision provides Vimba X for Mac; use Vimba X Viewer to verify camera connectivity before coding.

### Basler — Pylon

```bash
# Install Pylon SDK from Basler website (includes USB transport layer)
# Then install Python bindings:
pip install pypylon
# Verify:
python -c "from pypylon import pylon; print(pylon.GetPylonVersion())"
```

- pypylon wheels are available for Windows, Linux, macOS.
- Basler and Allied Vision USB transport layers can coexist; each SDK only claims its own cameras.

---

## Development Phases

### Phase 1 — Camera Abstraction + Single-Camera Live View
1. Implement `AlliedVisionCamera(CameraInterface)` with VmbPy.
2. Implement `BaslerCamera(CameraInterface)` with pypylon.
3. Build minimal PyQt window with one live viewport. Test each camera independently.
4. Validate frame rates, exposure control, pixel format switching.

### Phase 2 — Dual Live View + Controls
1. Dual-viewport layout with independent controls.
2. Camera discovery and auto-assignment by serial.
3. Histogram widget, scale bar overlay.
4. Filter selector for Basler.

### Phase 3 — Recording Engine
1. TIFF stack writer (threaded, ring-buffer backed, 2-second pre-trigger).
2. JSON metadata generation with OES sync fields.
3. Post-acquisition H.265 encoding pipeline (background FFmpeg queue).

### Phase 4 — OES App Integration + Polish
1. ZeroMQ PUB/SUB bus (`ipc_bus.py`) — camera app subscriber + publisher.
2. Add ZMQ publisher to OES Flash Plasma app record button (OES-side change).
3. Timestamp alignment and per-frame data publishing for OES log sync.
4. Keyboard shortcuts, dark theme, crash recovery.
5. Export utilities and documentation.

---

## Open Questions / Items to Verify

- [x] ~~**Basler FOV**~~: Confirmed 54 × 54 mm.
- [x] ~~**USB bandwidth**~~: Confirmed separate USB3 root hubs.
- [x] ~~**Trigger**~~: Software trigger via ZeroMQ from OES Flash Plasma app (PyQt6). Standalone trigger also available in camera app GUI.
- [x] ~~**Filter automation**~~: No plans — manual swap with software logging.
- [x] ~~**OES app framework**~~: PyQt6 — using ZeroMQ PUB/SUB for IPC.
- [x] ~~**Pre-trigger buffer**~~: 2 seconds (~1.4 GB RAM for both cameras at 30 fps Mono12).
- [x] ~~**OES integration depth**~~: Full sync — shared session IDs, cross-referenced file paths, per-frame data published on ZMQ bus for OES app to log alongside spectra.
- [x] ~~**Session directory structure**~~: Defined — `D:/flash_data/YYYY-MM-DD/session_name/` with per-camera subdirectories.
- [ ] **Storage drive**: NVMe SSD required for Maximum/High presets (~720 MB/s and ~400–550 MB/s). SATA SSD (~500 MB/s) is sufficient for Balanced, Fast, and Compact presets. Budget ~43 GB/min (Maximum) to ~6 GB/min (Compact) for dual-camera recording.
- [ ] **OES app modifications needed**: The OES Flash Plasma app will need a ZMQ publisher added to its record button handler and a subscriber for camera status. Estimate scope of changes needed on the OES side.
- [ ] **Camera serial numbers**: Replace `ALLIED_VISION_SERIAL_HERE` and `BASLER_SERIAL_HERE` in `default_config.yaml` with actual serials before first run.
