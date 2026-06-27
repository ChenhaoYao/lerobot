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

from ..config import TeleoperatorConfig

# Default 14-DOF dual-arm joint names (must match DualArmZMQRobotConfig.joint_names)
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


@TeleoperatorConfig.register_subclass("vr_zmq")
@dataclass
class VRZMQTeleopConfig(TeleoperatorConfig):
    """Configuration for the VR teleoperation interface bridged via ZMQ.

    The zmq_bridge_node in dual_arm subscribes to the VR ROS2 topic and
    re-publishes as a ZMQ PUB on action_port. This class subscribes to that port.

    NOTE: VR side is not yet implemented. Until it is, get_action() returns the last
    known action (or zeros) and logs a warning.
    """

    zmq_host: str = "localhost"
    action_port: int = 5557
    zmq_timeout_ms: int = 100
    joint_names: list[str] = field(default_factory=lambda: list(_DEFAULT_JOINT_NAMES))
