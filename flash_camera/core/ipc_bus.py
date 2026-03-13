"""ZeroMQ PUB/SUB IPC bus for OES application communication."""

import json
import logging
import time

import zmq
from PyQt6.QtCore import QThread, QTimer, pyqtSignal, QObject

logger = logging.getLogger(__name__)


class IPCPublisher:

    def __init__(self, port: int = 5556):
        self._port = port
        self._context: zmq.Context | None = None
        self._socket: zmq.Socket | None = None

    def start(self) -> None:
        self._context = zmq.Context()
        self._socket = self._context.socket(zmq.PUB)
        self._socket.bind(f"tcp://*:{self._port}")
        logger.info("IPCPublisher bound to tcp://*:%d", self._port)

    def stop(self) -> None:
        if self._socket is not None:
            self._socket.close(linger=100)
            self._socket = None
        if self._context is not None:
            self._context.term()
            self._context = None
        logger.info("IPCPublisher stopped")

    def publish_status(self, topic: str, payload: dict) -> None:
        if self._socket is None:
            return
        msg = json.dumps(payload, default=str)
        self._socket.send_multipart([topic.encode(), msg.encode()])

    def publish_heartbeat(
        self,
        cameras_connected: list[str],
        is_recording: bool,
        buffer_depth_s: float,
    ) -> None:
        self.publish_status("status/heartbeat", {
            "cameras_connected": cameras_connected,
            "is_recording": is_recording,
            "buffer_depth_s": buffer_depth_s,
            "timestamp_ns": time.time_ns(),
        })

    def publish_recording_state(
        self, state: str, session_id: str, frame_counts: dict,
    ) -> None:
        self.publish_status("status/recording", {
            "state": state,
            "session_id": session_id,
            "frame_counts": frame_counts,
        })

    def publish_frame_info(
        self,
        camera_id: str,
        frame_id: int,
        timestamp_ns: int,
        mean_intensity: float,
    ) -> None:
        self.publish_status(f"status/frame/{camera_id}", {
            "camera_id": camera_id,
            "frame_id": frame_id,
            "timestamp_ns": timestamp_ns,
            "mean_intensity": mean_intensity,
        })


class IPCSubscriber(QThread):

    record_start_received = pyqtSignal(dict)
    record_stop_received = pyqtSignal(dict)
    ping_received = pyqtSignal()
    heartbeat_timeout = pyqtSignal()

    HEARTBEAT_TIMEOUT_MS = 5000

    def __init__(self, port: int = 5555, parent: QObject | None = None):
        super().__init__(parent)
        self._port = port
        self._running = False
        self._last_heartbeat_ns = 0

    def stop(self) -> None:
        self._running = False
        self.wait(3000)

    def run(self) -> None:
        self._running = True
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(f"tcp://localhost:{self._port}")
        socket.subscribe(b"cmd/")
        socket.setsockopt(zmq.RCVTIMEO, 500)

        logger.info("IPCSubscriber connected to tcp://localhost:%d", self._port)

        while self._running:
            try:
                parts = socket.recv_multipart()
            except zmq.Again:
                self._check_heartbeat()
                continue

            if len(parts) < 2:
                continue

            topic = parts[0].decode(errors="replace")
            try:
                payload = json.loads(parts[1].decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Malformed payload on topic %s", topic)
                continue

            self._last_heartbeat_ns = time.time_ns()

            if topic == "cmd/record_start":
                self.record_start_received.emit(payload)
            elif topic == "cmd/record_stop":
                self.record_stop_received.emit(payload)
            elif topic == "cmd/ping":
                self.ping_received.emit()
            else:
                logger.debug("Unknown command topic: %s", topic)

        socket.close(linger=100)
        context.term()
        logger.info("IPCSubscriber stopped")

    def _check_heartbeat(self) -> None:
        if self._last_heartbeat_ns == 0:
            return
        elapsed_ms = (time.time_ns() - self._last_heartbeat_ns) / 1_000_000
        if elapsed_ms > self.HEARTBEAT_TIMEOUT_MS:
            self.heartbeat_timeout.emit()
            self._last_heartbeat_ns = 0


class IPCBus(QObject):

    record_start_received = pyqtSignal(dict)
    record_stop_received = pyqtSignal(dict)
    ping_received = pyqtSignal()
    heartbeat_timeout = pyqtSignal()

    def __init__(
        self,
        pub_port: int = 5556,
        sub_port: int = 5555,
        heartbeat_interval_s: float = 1.0,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self._publisher = IPCPublisher(port=pub_port)
        self._subscriber = IPCSubscriber(port=sub_port)
        self._heartbeat_interval_ms = int(heartbeat_interval_s * 1000)

        self._heartbeat_timer: QTimer | None = None
        self._cameras_connected: list[str] = []
        self._is_recording = False
        self._buffer_depth_s = 0.0

        self._subscriber.record_start_received.connect(self.record_start_received)
        self._subscriber.record_stop_received.connect(self.record_stop_received)
        self._subscriber.ping_received.connect(self.ping_received)
        self._subscriber.heartbeat_timeout.connect(self.heartbeat_timeout)

    @property
    def publisher(self) -> IPCPublisher:
        return self._publisher

    @property
    def subscriber(self) -> IPCSubscriber:
        return self._subscriber

    @property
    def is_oes_connected(self) -> bool:
        if self._subscriber._last_heartbeat_ns == 0:
            return False
        elapsed_ms = (time.time_ns() - self._subscriber._last_heartbeat_ns) / 1_000_000
        return elapsed_ms < IPCSubscriber.HEARTBEAT_TIMEOUT_MS

    def start(self) -> None:
        self._publisher.start()
        self._subscriber.start()

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)
        self._heartbeat_timer.start(self._heartbeat_interval_ms)

        logger.info("IPCBus started (pub=%d, sub=%d)", self._publisher._port, self._subscriber._port)

    def stop(self) -> None:
        if self._heartbeat_timer is not None:
            self._heartbeat_timer.stop()
            self._heartbeat_timer = None

        self._subscriber.stop()
        self._publisher.stop()
        logger.info("IPCBus stopped")

    def set_status(
        self,
        cameras_connected: list[str] | None = None,
        is_recording: bool | None = None,
        buffer_depth_s: float | None = None,
    ) -> None:
        if cameras_connected is not None:
            self._cameras_connected = cameras_connected
        if is_recording is not None:
            self._is_recording = is_recording
        if buffer_depth_s is not None:
            self._buffer_depth_s = buffer_depth_s

    def _send_heartbeat(self) -> None:
        self._publisher.publish_heartbeat(
            cameras_connected=self._cameras_connected,
            is_recording=self._is_recording,
            buffer_depth_s=self._buffer_depth_s,
        )
