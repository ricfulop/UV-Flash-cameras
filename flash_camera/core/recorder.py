"""Recording engine — TIFF frame writer and H.265 encoding."""

import glob
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import tifffile

from flash_camera.core.camera_interface import FrameMetadata
from flash_camera.core.quality_presets import QualityPreset

logger = logging.getLogger(__name__)

MAX_QUEUE_DEPTH = 200


class TiffWriter:

    def __init__(
        self,
        output_dir: str,
        camera_id: str,
        compression: str = "none",
        single_files: bool = True,
    ):
        self._output_dir = Path(output_dir)
        self._camera_id = camera_id
        self._compression = compression
        self._single_files = single_files

        self._queue: queue.Queue[tuple[np.ndarray, FrameMetadata] | None] = queue.Queue()
        self._frames_written = 0
        self._frames_dropped = 0
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        self._output_dir.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._writer_loop,
            name=f"tiff-writer-{self._camera_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("TiffWriter started for camera %s -> %s", self._camera_id, self._output_dir)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        logger.info(
            "TiffWriter stopped for camera %s — %d written, %d dropped",
            self._camera_id, self._frames_written, self._frames_dropped,
        )

    def flush(self) -> None:
        self._queue.join()

    def write_frame(self, frame: np.ndarray, metadata: FrameMetadata) -> None:
        depth = self._queue.qsize()
        if depth >= MAX_QUEUE_DEPTH:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                with self._lock:
                    self._frames_dropped += 1
                logger.warning(
                    "Queue overflow (%d) for camera %s — dropping oldest frame",
                    depth, self._camera_id,
                )
            except queue.Empty:
                pass
        self._queue.put((frame, metadata))

    def get_queue_depth(self) -> int:
        return self._queue.qsize()

    def get_frames_written(self) -> int:
        with self._lock:
            return self._frames_written

    def _writer_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            frame, metadata = item
            try:
                self._write_single(frame, metadata)
            except Exception:
                logger.exception("Write failed for frame %d, retrying uncompressed", metadata.frame_id)
                try:
                    self._write_single(frame, metadata, force_uncompressed=True)
                except Exception:
                    logger.exception("Uncompressed fallback also failed for frame %d", metadata.frame_id)
            self._queue.task_done()

    def _write_single(
        self, frame: np.ndarray, metadata: FrameMetadata, force_uncompressed: bool = False,
    ) -> None:
        compression = None if (self._compression == "none" or force_uncompressed) else self._compression

        if self._single_files:
            filename = f"frame_{metadata.frame_id:08d}.tiff"
            filepath = self._output_dir / filename
            extra_tags = [
                ("ImageDescription", "s", 0,
                 f"ts={metadata.timestamp_ns};exp={metadata.exposure_us};gain={metadata.gain_db};"
                 f"cam={metadata.camera_id};fmt={metadata.pixel_format}", True),
            ]
            tifffile.imwrite(
                str(filepath),
                frame,
                compression=compression,
                extratags=extra_tags,
            )
        else:
            filepath = self._output_dir / f"{self._camera_id}.tiff"
            with tifffile.TiffWriter(str(filepath), append=True) as tw:
                tw.write(frame, compression=compression)

        with self._lock:
            self._frames_written += 1


class H265Encoder:

    def __init__(
        self,
        tiff_dir: str,
        output_path: str,
        crf: int = 20,
        downscale_height: int = 1080,
    ):
        self._tiff_dir = Path(tiff_dir)
        self._output_path = Path(output_path)
        self._crf = crf
        self._downscale_height = downscale_height

        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._progress = 0.0
        self._running = False
        self._cancelled = False
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._cancelled = False
        self._thread = threading.Thread(
            target=self._encode_loop,
            name=f"h265-encoder-{self._output_path.stem}",
            daemon=True,
        )
        self._thread.start()
        logger.info("H265Encoder started: %s -> %s", self._tiff_dir, self._output_path)

    def get_progress(self) -> float:
        with self._lock:
            return self._progress

    def is_running(self) -> bool:
        return self._running

    def cancel(self) -> None:
        self._cancelled = True
        if self._process is not None:
            try:
                self._process.terminate()
            except OSError:
                pass
        logger.info("H265Encoder cancelled for %s", self._output_path)

    def _encode_loop(self) -> None:
        try:
            tiff_files = sorted(glob.glob(str(self._tiff_dir / "frame_*.tiff")))
            if not tiff_files:
                logger.warning("No TIFF files found in %s", self._tiff_dir)
                return

            total = len(tiff_files)
            sample = tifffile.imread(tiff_files[0])
            h, w = sample.shape[:2]

            scale_factor = self._downscale_height / h
            out_w = int(w * scale_factor)
            out_h = self._downscale_height
            if out_w % 2 != 0:
                out_w += 1

            pix_fmt = "gray" if sample.ndim == 2 else "rgb24"
            input_dtype_bytes = sample.dtype.itemsize

            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-pix_fmt", "gray16le" if input_dtype_bytes == 2 else pix_fmt,
                "-s", f"{w}x{h}",
                "-r", "30",
                "-i", "pipe:0",
                "-vf", f"scale={out_w}:{out_h}",
                "-c:v", "libx265",
                "-crf", str(self._crf),
                "-pix_fmt", "yuv420p",
                "-tag:v", "hvc1",
                str(self._output_path),
            ]

            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            for i, path in enumerate(tiff_files):
                if self._cancelled:
                    break
                frame = tifffile.imread(path)
                if frame.dtype == np.uint16 and input_dtype_bytes == 1:
                    frame = (frame >> 4).astype(np.uint8)
                self._process.stdin.write(frame.tobytes())
                with self._lock:
                    self._progress = (i + 1) / total

            self._process.stdin.close()
            self._process.wait()

            if self._process.returncode != 0 and not self._cancelled:
                stderr = self._process.stderr.read().decode(errors="replace")
                logger.error("ffmpeg exited %d: %s", self._process.returncode, stderr[-500:])
            elif not self._cancelled:
                logger.info("H265 encode complete: %s", self._output_path)

        except Exception:
            logger.exception("H265 encoding failed for %s", self._output_path)
        finally:
            self._running = False
            self._process = None


class RecordingSession:

    def __init__(
        self,
        data_root: str,
        session_name: str,
        quality_preset: QualityPreset,
        cameras: list[str],
    ):
        self._data_root = Path(data_root)
        self._session_name = session_name
        self._quality_preset = quality_preset
        self._cameras = cameras

        date_str = datetime.now().strftime("%Y-%m-%d")
        self._session_dir = self._data_root / date_str / session_name

        self._writers: dict[str, TiffWriter] = {}
        self._start_time: float | None = None
        self._stop_time: float | None = None

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    def start(self) -> None:
        self._start_time = time.monotonic()
        for cam_id in self._cameras:
            cam_dir = self._session_dir / cam_id
            cam_dir.mkdir(parents=True, exist_ok=True)
            writer = TiffWriter(
                output_dir=str(cam_dir),
                camera_id=cam_id,
                compression=self._quality_preset.tiff_compression,
            )
            writer.start()
            self._writers[cam_id] = writer
        logger.info("RecordingSession started: %s (%d cameras)", self._session_dir, len(self._cameras))

    def write_frame(self, camera_id: str, frame: np.ndarray, metadata: FrameMetadata) -> None:
        writer = self._writers.get(camera_id)
        if writer is None:
            logger.error("No writer for camera %s", camera_id)
            return
        writer.write_frame(frame, metadata)

    def stop(self) -> dict:
        self._stop_time = time.monotonic()
        stats = self.get_stats()
        for writer in self._writers.values():
            writer.stop()
        logger.info("RecordingSession stopped: %s", self._session_dir)
        return stats

    def get_stats(self) -> dict:
        elapsed = 0.0
        if self._start_time is not None:
            end = self._stop_time if self._stop_time is not None else time.monotonic()
            elapsed = end - self._start_time

        per_camera = {}
        for cam_id, writer in self._writers.items():
            written = writer.get_frames_written()
            per_camera[cam_id] = {
                "frames_written": written,
                "queue_depth": writer.get_queue_depth(),
                "write_rate_fps": written / elapsed if elapsed > 0 else 0.0,
            }

        return {
            "session_dir": str(self._session_dir),
            "session_name": self._session_name,
            "preset": self._quality_preset.name,
            "elapsed_s": elapsed,
            "cameras": per_camera,
        }

    def encode_previews(self) -> list[H265Encoder]:
        encoders = []
        for cam_id in self._cameras:
            cam_dir = self._session_dir / cam_id
            output_path = self._session_dir / f"{cam_id}_preview.mp4"
            encoder = H265Encoder(
                tiff_dir=str(cam_dir),
                output_path=str(output_path),
            )
            encoder.start()
            encoders.append(encoder)
        return encoders
