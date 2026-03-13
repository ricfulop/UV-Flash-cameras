"""
Synchronized timestamps across cameras.
"""
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_system_time_ns() -> int:
    return time.perf_counter_ns()


def get_utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_date_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_time_string() -> str:
    return datetime.now(timezone.utc).strftime("%H%M%S")


def compute_clock_offset(camera_ts_ns: int, system_ts_ns: int) -> int:
    return system_ts_ns - camera_ts_ns


class TimestampSynchronizer:
    def __init__(self) -> None:
        self._refs: dict[str, tuple[int, str]] = {}

    def register_camera(self, camera_id: str) -> None:
        perf_ns = get_system_time_ns()
        utc = get_utc_timestamp()
        self._refs[camera_id] = (perf_ns, utc)
        logger.debug("Registered camera %s: perf_ns=%d, utc=%s", camera_id, perf_ns, utc)

    def camera_to_utc(self, camera_id: str, camera_ts_ns: int) -> str:
        if camera_id not in self._refs:
            logger.warning("Camera %s not registered, returning raw timestamp", camera_id)
            return get_utc_timestamp()
        ref_perf_ns, ref_utc = self._refs[camera_id]
        ref_dt = datetime.fromisoformat(ref_utc.replace("Z", "+00:00"))
        ref_epoch_ns = int(ref_dt.timestamp() * 1e9)
        offset_ns = camera_ts_ns - ref_perf_ns
        estimated_epoch_ns = ref_epoch_ns + offset_ns
        estimated_dt = datetime.fromtimestamp(estimated_epoch_ns / 1e9, tz=timezone.utc)
        return estimated_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def get_sync_info(self) -> dict:
        return {
            cam_id: {
                "ref_perf_ns": ref[0],
                "ref_utc": ref[1],
            }
            for cam_id, ref in self._refs.items()
        }
