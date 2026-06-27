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

from dataclasses import dataclass, field

from ..config import RobotConfig

# Default 14-DOF dual-arm joint names (left arm: laxis1-7, right arm: raxis1-7)
_DEFAULT_JOINT_NAMES = [
    "laxis1_joint",
    "laxis2_joint",
    "laxis3_joint",
    "laxis4_joint",
    "laxis5_joint",
    "laxis6_joint",
    "laxis7_joint",
    "raxis1_joint",
    "raxis2_joint",
    "raxis3_joint",
    "raxis4_joint",
    "raxis5_joint",
    "raxis6_joint",
    "raxis7_joint",
]


@RobotConfig.register_subclass("dual_arm_zmq")
@dataclass
class DualArmZMQRobotConfig(RobotConfig):
    """Configuration for the dual-arm robot bridged via ZMQ from the dual_arm ROS2 project.

    ZMQ ports layout:
        joints_port        : ZMQ PUB from bridge → lerobot reads joint states
        head_camera_port   : ZMQ PUB from bridge → lerobot reads head camera (ZMQCamera format)
        left_wrist_port    : ZMQ PUB from bridge → lerobot reads left wrist camera
        right_wrist_port   : ZMQ PUB from bridge → lerobot reads right wrist camera
        action_port        : lerobot PUSH → bridge PULL, forwards actions to JTC (inference only)
    """

    zmq_host: str = "localhost"
    joints_port: int = 5556
    head_camera_port: int = 5555
    left_wrist_port: int = 5559
    right_wrist_port: int = 5560
    action_port: int = 5558
    camera_width: int = 640
    camera_height: int = 480
    camera_fps: int = 30
    zmq_timeout_ms: int = 1000
    joint_names: list[str] = field(default_factory=lambda: list(_DEFAULT_JOINT_NAMES))
