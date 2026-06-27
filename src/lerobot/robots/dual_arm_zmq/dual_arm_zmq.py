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
DualArmZMQRobot — lerobot Robot adapter for the dual_arm ROS2 project.

Data flow (recording / teleoperation):
    dual_arm zmq_bridge_node  ──ZMQ PUB──▶  DualArmZMQRobot.get_observation()
    DualArmZMQRobot.send_action()  ──ZMQ PUSH──▶  dual_arm zmq_bridge_node  ──▶  JTC

Camera images are received via the existing ZMQCamera class (same protocol as image_server.py).
"""

import json
import logging
import time
from functools import cached_property
from threading import Event, Lock, Thread
from typing import Any

import numpy as np

from lerobot.cameras.zmq import ZMQCamera, ZMQCameraConfig
from lerobot.processor import RobotAction, RobotObservation
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..robot import Robot
from .config_dual_arm_zmq import DualArmZMQRobotConfig

logger = logging.getLogger(__name__)


class DualArmZMQRobot(Robot):
    """
    Robot adapter that receives observations (joint states + camera images) and sends actions
    to the dual_arm ROS2 project via ZeroMQ.

    Expected ZMQ protocol from zmq_bridge_node:
        joints_port  : PUB, JSON {"names": [...], "positions": [...], "velocities": [...], "timestamp": float}
        camera ports : PUB, JSON {"timestamps": {cam_name: float}, "images": {cam_name: "<base64-jpeg>"}}
        action_port  : PUSH (lerobot) / PULL (bridge), JSON {"joint_positions": {name: float}, "timestamp": float}
    """

    config_class = DualArmZMQRobotConfig
    name = "dual_arm_zmq"

    def __init__(self, config: DualArmZMQRobotConfig):
        super().__init__(config)
        self.config = config

        self._connected = False

        # ZMQ resources (joint states)
        self._zmq_context: Any = None
        self._joint_sub: Any = None
        self._action_push: Any = None

        # Latest cached joint state
        self._joint_lock = Lock()
        self._latest_joints: dict[str, float] | None = None
        self._joint_thread: Thread | None = None
        self._joint_stop: Event | None = None

        # Camera instances (keyed by logical name)
        self.cameras: dict[str, ZMQCamera] = {
            "head_camera": ZMQCamera(
                ZMQCameraConfig(
                    server_address=config.zmq_host,
                    port=config.head_camera_port,
                    camera_name="head_camera",
                    width=config.camera_width,
                    height=config.camera_height,
                    fps=config.camera_fps,
                )
            ),
            "left_wrist_camera": ZMQCamera(
                ZMQCameraConfig(
                    server_address=config.zmq_host,
                    port=config.left_wrist_port,
                    camera_name="left_wrist_camera",
                    width=config.camera_width,
                    height=config.camera_height,
                    fps=config.camera_fps,
                )
            ),
            "right_wrist_camera": ZMQCamera(
                ZMQCameraConfig(
                    server_address=config.zmq_host,
                    port=config.right_wrist_port,
                    camera_name="right_wrist_camera",
                    width=config.camera_width,
                    height=config.camera_height,
                    fps=config.camera_fps,
                )
            ),
        }

    # ------------------------------------------------------------------
    # Feature declarations
    # ------------------------------------------------------------------

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        motor_ft = {f"{j}.pos": float for j in self.config.joint_names}
        cam_ft = {
            cam_name: (self.config.camera_height, self.config.camera_width, 3)
            for cam_name in self.cameras
        }
        return {**motor_ft, **cam_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return {f"{j}.pos": float for j in self.config.joint_names}

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

        # Joint state subscriber
        self._joint_sub = self._zmq_context.socket(zmq.SUB)
        self._joint_sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self._joint_sub.setsockopt(zmq.RCVTIMEO, self.config.zmq_timeout_ms)
        self._joint_sub.setsockopt(zmq.CONFLATE, True)
        self._joint_sub.connect(f"tcp://{self.config.zmq_host}:{self.config.joints_port}")

        # Action push socket (for inference; no-op during pure teleoperation recording)
        self._action_push = self._zmq_context.socket(zmq.PUSH)
        self._action_push.setsockopt(zmq.SNDHWM, 1)
        self._action_push.setsockopt(zmq.LINGER, 0)
        self._action_push.connect(f"tcp://{self.config.zmq_host}:{self.config.action_port}")

        # Start background thread for joint state polling
        self._joint_stop = Event()
        self._joint_thread = Thread(
            target=self._joint_read_loop, daemon=True, name="dual_arm_joint_reader"
        )
        self._joint_thread.start()

        # Wait for first joint state (warmup)
        deadline = time.time() + self.config.zmq_timeout_ms / 1000.0
        while time.time() < deadline:
            with self._joint_lock:
                if self._latest_joints is not None:
                    break
            time.sleep(0.05)
        else:
            self._cleanup_zmq()
            raise ConnectionError(
                f"[{self}] No joint state received from ZMQ port {self.config.joints_port} "
                f"within {self.config.zmq_timeout_ms}ms. "
                "Check that zmq_bridge_node is running."
            )

        # Connect cameras
        for cam_name, cam in self.cameras.items():
            logger.info(f"[{self}] Connecting camera: {cam_name}")
            cam.connect()

        self._connected = True
        logger.info(f"[{self}] connected.")

    @check_if_not_connected
    def disconnect(self) -> None:
        self._connected = False

        if self._joint_stop is not None:
            self._joint_stop.set()
        if self._joint_thread is not None and self._joint_thread.is_alive():
            self._joint_thread.join(timeout=2.0)

        for cam_name, cam in self.cameras.items():
            if cam.is_connected:
                cam.disconnect()
                logger.debug(f"[{self}] Camera {cam_name} disconnected.")

        self._cleanup_zmq()
        logger.info(f"[{self}] disconnected.")

    def _cleanup_zmq(self) -> None:
        if self._joint_sub is not None:
            self._joint_sub.close()
            self._joint_sub = None
        if self._action_push is not None:
            self._action_push.close()
            self._action_push = None
        if self._zmq_context is not None:
            self._zmq_context.term()
            self._zmq_context = None

    # ------------------------------------------------------------------
    # Background joint state reader
    # ------------------------------------------------------------------

    def _joint_read_loop(self) -> None:
        """Background thread: continuously receive and cache the latest joint state."""
        assert self._joint_stop is not None
        failure_count = 0

        while not self._joint_stop.is_set():
            try:
                msg = self._joint_sub.recv_string()
                data = json.loads(msg)
                positions = {
                    name: float(pos)
                    for name, pos in zip(data["names"], data["positions"], strict=False)
                }
                with self._joint_lock:
                    self._latest_joints = positions
                failure_count = 0
            except Exception as e:
                if type(e).__name__ == "Again":
                    # ZMQ timeout — no new data, keep looping
                    continue
                failure_count += 1
                if failure_count <= 5:
                    logger.warning(f"[{self}] Joint state read error: {e}")
                else:
                    logger.error(f"[{self}] Too many joint state read errors, stopping thread.")
                    break

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        obs: RobotObservation = {}

        # Joint positions
        with self._joint_lock:
            joints = dict(self._latest_joints) if self._latest_joints else {}

        if not joints:
            logger.warning(f"[{self}] No joint state available, returning zeros.")
            joints = {j: 0.0 for j in self.config.joint_names}

        for joint_name in self.config.joint_names:
            obs[f"{joint_name}.pos"] = joints.get(joint_name, 0.0)

        # Camera images
        for cam_name, cam in self.cameras.items():
            start = time.perf_counter()
            obs[cam_name] = cam.async_read()
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"[{self}] Camera {cam_name} read: {dt_ms:.1f}ms")

        return obs

    @check_if_not_connected
    def send_action(self, action: RobotAction) -> RobotAction:
        """Forward joint position targets to dual_arm via ZMQ.

        During teleoperation recording, the bridge node receives these targets and forwards
        them to the ROS2 JointTrajectoryController. During pure observation-only recording,
        this method is still called but the bridge node is responsible for deciding whether
        to execute them.
        """
        joint_positions = {
            key.removesuffix(".pos"): float(val)
            for key, val in action.items()
            if key.endswith(".pos")
        }
        payload = json.dumps({"joint_positions": joint_positions, "timestamp": time.time()})
        try:
            import zmq
            self._action_push.send_string(payload, zmq.NOBLOCK)
        except Exception as e:
            if type(e).__name__ == "Again":
                logger.debug(f"[{self}] Action push buffer full, dropping frame.")
            else:
                logger.warning(f"[{self}] Failed to push action: {e}")

        return action

    def __str__(self) -> str:
        return f"DualArmZMQRobot(host={self.config.zmq_host})"
