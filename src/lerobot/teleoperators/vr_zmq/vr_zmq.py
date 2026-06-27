#!/usr/bin/env python

# Copyright 2026 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
VRZMQTeleop — receives VR teleoperation action commands via ZeroMQ.

Expected ZMQ publisher: zmq_bridge_node.py in dual_arm_bringup subscribes to
the VR ROS2 topic and forwards to ZMQ PUB on action_port.

Protocol (JSON):
    {"joint_positions": {"laxis1_joint": 0.0, ..., "raxis7_joint": 0.0}, "timestamp": float}

NOTE: The VR side of zmq_bridge_node is a TODO placeholder. Until it is implemented,
get_action() returns the last known positions (or zeros) and emits a warning.
"""

import json
import logging
import time
from threading import Event, Lock, Thread
from typing import Any

from lerobot.processor import RobotAction
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from ..teleoperator import Teleoperator
from .config_vr_zmq import VRZMQTeleopConfig

logger = logging.getLogger(__name__)


class VRZMQTeleop(Teleoperator):
    """
    Teleoperation interface that receives VR action commands via ZeroMQ.

    During recording, the dual_arm zmq_bridge_node relays VR joint targets
    (from the VR ROS2 topic) to this teleoperator over ZMQ.

    Interface contract:
        - `get_action()` returns the latest VR joint position targets as
          `{"{joint_name}.pos": float, ...}` to match `action_features`.
        - `send_feedback()` is a no-op (force feedback not yet implemented).

    TODO: VR integration in zmq_bridge_node.py must be completed before
          this teleoperator produces real data.
    """

    config_class = VRZMQTeleopConfig
    name = "vr_zmq"

    def __init__(self, config: VRZMQTeleopConfig):
        super().__init__(config)
        self.config = config

        self._connected = False
        self._zmq_context: Any = None
        self._action_sub: Any = None

        self._lock = Lock()
        self._latest_action: dict[str, float] | None = None
        self._recv_thread: Thread | None = None
        self._stop_event: Event | None = None

    # ------------------------------------------------------------------
    # Feature declarations
    # ------------------------------------------------------------------

    @property
    def action_features(self) -> dict[str, type]:
        return {f"{j}.pos": float for j in self.config.joint_names}

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Connect / Disconnect
    # ------------------------------------------------------------------

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        import zmq

        self._zmq_context = zmq.Context()
        self._action_sub = self._zmq_context.socket(zmq.SUB)
        self._action_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self._action_sub.setsockopt(zmq.RCVTIMEO, self.config.zmq_timeout_ms)
        self._action_sub.setsockopt(zmq.CONFLATE, True)
        self._action_sub.connect(f"tcp://{self.config.zmq_host}:{self.config.action_port}")

        self._stop_event = Event()
        self._recv_thread = Thread(
            target=self._recv_loop, daemon=True, name="vr_zmq_recv"
        )
        self._recv_thread.start()

        self._connected = True
        logger.info(
            f"[{self}] connected to ZMQ port {self.config.action_port}. "
            "NOTE: VR side not yet implemented — get_action() will return zeros until VR is ready."
        )

    @check_if_not_connected
    def disconnect(self) -> None:
        self._connected = False
        if self._stop_event is not None:
            self._stop_event.set()
        if self._recv_thread is not None and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)
        if self._action_sub is not None:
            self._action_sub.close()
            self._action_sub = None
        if self._zmq_context is not None:
            self._zmq_context.term()
            self._zmq_context = None
        logger.info(f"[{self}] disconnected.")

    # ------------------------------------------------------------------
    # Background receiver
    # ------------------------------------------------------------------

    def _recv_loop(self) -> None:
        """Background thread: continuously receive and cache the latest VR action."""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                msg = self._action_sub.recv_string()
                data = json.loads(msg)
                joint_positions: dict[str, float] = {
                    k: float(v) for k, v in data["joint_positions"].items()
                }
                with self._lock:
                    self._latest_action = joint_positions
            except Exception as e:
                if type(e).__name__ == "Again":
                    continue
                logger.debug(f"[{self}] VR recv error: {e}")

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @check_if_not_connected
    def get_action(self) -> RobotAction:
        """Return the latest VR joint position targets.

        Returns zeros for all joints if no VR data has been received yet.
        This is expected while the VR side of zmq_bridge_node is not yet implemented.
        """
        with self._lock:
            latest = dict(self._latest_action) if self._latest_action is not None else None

        if latest is None:
            logger.warning(
                f"[{self}] No VR action received yet (VR side not implemented). "
                "Returning zeros. Implement VR subscription in zmq_bridge_node.py."
            )
            return {f"{j}.pos": 0.0 for j in self.config.joint_names}

        return {f"{j}.pos": latest.get(j, 0.0) for j in self.config.joint_names}

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        pass

    def __str__(self) -> str:
        return f"VRZMQTeleop(host={self.config.zmq_host}, port={self.config.action_port})"
