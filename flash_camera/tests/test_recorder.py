"""Tests for recording engine components."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from flash_camera.core.camera_interface import FrameMetadata
from flash_camera.core.frame_buffer import FrameRingBuffer
from flash_camera.core.quality_presets import (
    PRESETS,
    QualityPreset,
    dtype_for_bit_depth,
    estimate_storage_rate,
    estimate_storage_per_minute,
    get_preset,
)


class TestFrameRingBuffer:

    def test_push_and_depth(self):
        buf = FrameRingBuffer(duration_s=1.0, max_fps=10.0, width=64, height=48)
        assert buf.get_depth() == 0

        frame = np.zeros((48, 64), dtype=np.uint16)
        meta = FrameMetadata(
            timestamp_ns=1000, frame_id=0, exposure_us=100,
            gain_db=0, camera_id="test", pixel_format="Mono12",
        )
        buf.push(frame, meta)
        assert buf.get_depth() == 1

    def test_overflow_wraps(self):
        buf = FrameRingBuffer(duration_s=0.5, max_fps=4.0, width=64, height=48)
        for i in range(10):
            frame = np.full((48, 64), i, dtype=np.uint16)
            meta = FrameMetadata(
                timestamp_ns=i * 1_000_000_000, frame_id=i, exposure_us=100,
                gain_db=0, camera_id="test", pixel_format="Mono12",
            )
            buf.push(frame, meta)
        assert buf.get_depth() == 2

    def test_flush(self):
        buf = FrameRingBuffer(duration_s=1.0, max_fps=5.0, width=64, height=48)
        for i in range(3):
            frame = np.full((48, 64), i * 10, dtype=np.uint16)
            meta = FrameMetadata(
                timestamp_ns=i * 1_000_000_000, frame_id=i, exposure_us=100,
                gain_db=0, camera_id="test", pixel_format="Mono12",
            )
            buf.push(frame, meta)

        flushed = buf.flush()
        assert len(flushed) == 3
        assert buf.get_depth() == 0
        assert flushed[0][1].frame_id == 0
        assert flushed[2][1].frame_id == 2

    def test_clear(self):
        buf = FrameRingBuffer(duration_s=1.0, max_fps=5.0, width=64, height=48)
        frame = np.zeros((48, 64), dtype=np.uint16)
        meta = FrameMetadata(
            timestamp_ns=0, frame_id=0, exposure_us=100,
            gain_db=0, camera_id="test", pixel_format="Mono12",
        )
        buf.push(frame, meta)
        buf.clear()
        assert buf.get_depth() == 0

    def test_resize(self):
        buf = FrameRingBuffer(duration_s=1.0, max_fps=5.0, width=64, height=48)
        buf.resize(duration_s=2.0, max_fps=10.0, width=128, height=96)
        frame = np.zeros((96, 128), dtype=np.uint16)
        meta = FrameMetadata(
            timestamp_ns=0, frame_id=0, exposure_us=100,
            gain_db=0, camera_id="test", pixel_format="Mono12",
        )
        buf.push(frame, meta)
        assert buf.get_depth() == 1


class TestQualityPresets:

    def test_all_presets_exist(self):
        for name in ("maximum", "high", "balanced", "fast", "compact", "custom"):
            preset = get_preset(name)
            assert preset.name == name

    def test_unknown_preset_raises(self):
        with pytest.raises(KeyError):
            get_preset("nonexistent")

    def test_dtype_for_bit_depth(self):
        assert dtype_for_bit_depth("Mono8") == np.dtype(np.uint8)
        assert dtype_for_bit_depth("Mono12") == np.dtype(np.uint16)
        assert dtype_for_bit_depth("Mono16") == np.dtype(np.uint16)
        with pytest.raises(ValueError):
            dtype_for_bit_depth("RGB24")

    def test_storage_estimates(self):
        preset = get_preset("maximum")
        rate = estimate_storage_rate(preset)
        assert rate > 0
        gb_min = estimate_storage_per_minute(preset)
        assert gb_min > 0

    def test_compression_reduces_estimate(self):
        raw = estimate_storage_rate(get_preset("maximum"))
        compressed = estimate_storage_rate(get_preset("high"))
        assert compressed < raw


class TestTiffWriter:

    def test_write_and_read(self):
        import tifffile
        from flash_camera.core.recorder import TiffWriter

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = TiffWriter(output_dir=tmpdir, camera_id="test", compression="none")
            writer.start()

            frame = np.random.randint(0, 4095, (48, 64), dtype=np.uint16)
            meta = FrameMetadata(
                timestamp_ns=1234567890, frame_id=0, exposure_us=100,
                gain_db=0, camera_id="test", pixel_format="Mono12",
            )
            writer.write_frame(frame, meta)
            writer.stop()

            assert writer.get_frames_written() == 1
            written_files = list(Path(tmpdir).glob("frame_*.tiff"))
            assert len(written_files) == 1
            loaded = tifffile.imread(str(written_files[0]))
            np.testing.assert_array_equal(frame, loaded)
