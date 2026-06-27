# LeRobot 数据集格式详解

> 以 `lerobot_zihao_dataset_shake_hands`（机械臂握手数据集）为实例，基于 v3.0 格式。

## 目录结构

```
lerobot_zihao_dataset_shake_hands/
├── meta/
│   ├── info.json                    # 数据集 schema：特征定义、维度、fps
│   ├── stats.json                   # 全局统计量 (min/max/mean/std/分位数)
│   ├── tasks.parquet                # 任务文本索引表
│   └── episodes/
│       └── chunk-000/
│           └── file-000.parquet     # 每集元数据 + 逐集统计量（30 行 × 93 列）
├── data/
│   └── chunk-000/
│       └── file-000.parquet         # 核心数据：每帧一行（10113 行 × 7 列）
└── videos/
    └── observation.images.front/
        └── chunk-000/
            ├── file-000.mp4         # 多集拼接的视频
            └── file-001.mp4
```

## info.json — 数据集定义

描述数据集的完整 schema，告诉加载器每个特征的类型和维度：

```json
{
  "codebase_version": "v3.0",
  "robot_type": "so101_follower",
  "total_episodes": 30,
  "total_frames": 10113,
  "fps": 30,
  "features": {
    "action":                    { "dtype": "float32", "shape": [6], "names": ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"] },
    "observation.state":         { "dtype": "float32", "shape": [6], "names": ["shoulder_pan.pos", "shoulder_lift.pos", "elbow_flex.pos", "wrist_flex.pos", "wrist_roll.pos", "gripper.pos"] },
    "observation.images.front":  { "dtype": "video",   "shape": [1080, 1920, 3], "names": ["height", "width", "channels"] },
    "timestamp":      { "dtype": "float32", "shape": [1], "names": null },
    "frame_index":    { "dtype": "int64",   "shape": [1], "names": null },
    "episode_index":  { "dtype": "int64",   "shape": [1], "names": null },
    "index":          { "dtype": "int64",   "shape": [1], "names": null },
    "task_index":     { "dtype": "int64",   "shape": [1], "names": null }
  }
}
```

**特征分类：**

| 类别 | 特征 | 说明 |
|------|------|------|
| 用户定义 | `action` | 6 维 float32，SO-101 的 6 个关节目标位置（度） |
| 用户定义 | `observation.state` | 6 维 float32，6 个关节当前位置（度） |
| 用户定义 | `observation.images.front` | 1080×1920 RGB 视频，存储为 mp4 |
| 自动添加 | `timestamp` | 帧在 episode 内的时间戳（秒）= frame_index / fps |
| 自动添加 | `frame_index` | 帧在 episode 内的序号（0-based） |
| 自动添加 | `episode_index` | 所属 episode 的序号 |
| 自动添加 | `index` | 全局帧序号（跨所有 episode） |
| 自动添加 | `task_index` | 指向 tasks.parquet 的任务索引 |

> 后 5 列由框架自动添加，创建数据集时无需手动指定。

## data/ — 核心数据 (Parquet)

每行是一帧，本数据集共 **10113 行**（30 个 episode × ~337 帧/episode）：

| 列名 | 示例值 | 说明 |
|------|--------|------|
| `index` | `0` | 全局帧序号，范围 [0, 10112] |
| `episode_index` | `0` | 所属 episode，范围 [0, 29] |
| `frame_index` | `0` | episode 内帧序号，范围 [0, 349] |
| `timestamp` | `0.0` | episode 内时间 = frame_index / 30fps |
| `task_index` | `0` | 指向 tasks.parquet 的第 0 行 |
| `observation.state` | `[-1.65, -99.16, 96.82, 63.25, 1.83, 1.46]` | 6 个关节当前位置 |
| `action` | `[-0.93, -99.58, 97.10, 60.54, 2.00, 0.56]` | 6 个关节目标位置 |

`observation.state` 是当前帧关节的实际读数，`action` 是发送给电机的目标值。在遥操作采集时两者接近但不完全相同（存在控制延迟和电机响应差异）。

**数据分片规则：** 多个 episode 的帧连续存放在同一个 parquet 文件中，单文件大小上限 100MB。本数据集 30 个 episode 全部在一个文件里。

## videos/ — 视频存储

视觉特征（`dtype: "video"`）以 mp4 文件存储，采用**多集拼接**方式减少文件数量：

```
videos/observation.images.front/
└── chunk-000/
    ├── file-000.mp4    ← episode 0~17 拼接（约 210 秒）
    └── file-001.mp4    ← episode 18~29 拼接
```

每个 episode 在拼接视频中的时间范围记录在 episode 元数据中：

| episode | from_timestamp | to_timestamp |
|---------|---------------|-------------|
| 0 | 0.000 | 11.667 |
| 1 | 11.667 | 23.300 |
| 2 | 23.300 | 34.967 |
| ... | ... | ... |

加载时通过 `torchcodec` 按时间戳定位解码，转为 `(C, H, W)` float32 `[0, 1]` 张量。

**备选存储方式：** 若 `dtype: "image"`，图像以 PNG 二进制直接嵌入 parquet 文件，不生成 mp4。

## tasks.parquet — 任务描述

```
              task_index
Shanke Hands           0
```

自然语言任务描述的索引表。所有帧的 `task_index=0` 均指向 "Shanke Hands"。此字段供 VLA 模型（如 SmolVLA）使用，ACT 等纯动作策略不读取它。

## episodes/ — 逐集元数据

每个 episode 一行，记录该集的边界信息和统计量：

| 字段 | 示例值 | 说明 |
|------|--------|------|
| `episode_index` | `0` | episode 序号 |
| `tasks` | `["Shanke Hands"]` | 该集的任务描述列表 |
| `length` | `350` | 帧数 |
| `dataset_from_index` | `0` | 在 data parquet 中的起始行 |
| `dataset_to_index` | `350` | 在 data parquet 中的结束行（不含） |
| `videos/observation.images.front/from_timestamp` | `0.0` | 在拼接视频中的起始时间 |
| `videos/observation.images.front/to_timestamp` | `11.667` | 在拼接视频中的结束时间 |
| `stats/action/min` | `[-13.92, -99.92, ...]` | 该集 action 的最小值 |
| `stats/action/max` | `[1.75, -28.95, ...]` | 该集 action 的最大值 |
| `stats/action/mean` | `[-3.41, -77.10, ...]` | 该集 action 的均值 |
| ... | ... | 其他统计量 (std, q01, q10, q50, q90, q99) |

## stats.json — 全局统计量

对全部 10113 帧计算的各特征统计量，用于训练时的归一化：

```json
{
  "observation.state": {
    "min":  [-19.62, -99.33, 8.03, -3.64, -5.05, 1.20],
    "max":  [2.02, 11.40, 99.27, 78.66, 14.14, 36.79],
    "mean": [-6.57, -68.43, 73.25, 45.96, 2.21, 10.20],
    "std":  [3.82, 34.90, 25.52, 18.92, 3.29, 9.10],
    "count": [10113],
    "q01": [...], "q10": [...], "q50": [...], "q90": [...], "q99": [...]
  },
  "action": { ... },
  "observation.images.front": { "min": [[[0.0]]], "max": [[[1.0]]], ... }
}
```

图像统计量按通道计算（shape `(3,1,1)`），值归一化到 `[0, 1]`。

## ACT 训练时的数据读取

### Delta Timestamps 机制

不同策略通过 `delta_timestamps` 从同一数据集提取不同的时间窗口：

| 策略 | observation_delta_indices | action_delta_indices | reward_delta_indices |
|------|--------------------------|---------------------|---------------------|
| ACT | `None`（仅当前帧） | `[0, 1, ..., chunk_size-1]`（默认 100 步） | `None` |
| Diffusion | `[-n_obs+1, ..., 0]` | `[-n_obs+1, ..., horizon-n_obs]` | `None` |
| TDMPC | `[0, ..., horizon]` | `[0, ..., horizon-1]` | `[0, ..., horizon-1]` |
| SmolVLA | `[0]` | `[0, 1, ..., chunk_size-1]` | `None` |

### ACT 的 `__getitem__()` 返回值

对于数据集中的第 t 帧：

```python
{
    "observation.state":         shape (6,)           # 第 t 帧的关节状态
    "observation.images.front":  shape (3, 1080, 1920) # 第 t 帧的图像 (解码自 mp4)
    "action":                    shape (100, 6)        # 第 t~t+99 帧的动作序列
    "action_is_pad":             shape (100,)          # 超出 episode 边界的位置为 True
    "index":          scalar
    "episode_index":  scalar
    "frame_index":    scalar
    "timestamp":      scalar
    "task_index":     scalar
    "task":           "Shanke Hands"  # 字符串
}
```

`action_is_pad` 的作用：当 t 靠近 episode 末尾时，t+1 到 t+99 可能超出边界，这些位置的 action 用零填充，`action_is_pad` 对应位置标 `True`，ACT 的 L1 loss 会屏蔽这些位置。

### ACT `forward(batch)` 读取的 key

| Batch Key | Shape | 用途 |
|-----------|-------|------|
| `observation.state` | `(B, 6)` | VAE encoder + transformer encoder 输入 |
| `observation.images.*` | `(B, 3, H, W)` | ResNet backbone 输入 |
| `action` | `(B, 100, 6)` | VAE encoder 目标 + L1 loss |
| `action_is_pad` | `(B, 100)` | loss mask，屏蔽填充帧 |

## v2.1 与 v3.0 格式差异

| 方面 | v2.1 | v3.0 |
|------|------|------|
| 数据文件 | 每 episode 一个 parquet | 多 episode 合并，按大小分片（上限 100MB） |
| 视频文件 | 每 episode 每相机一个 mp4 | 多 episode 拼接为一个 mp4（上限 200MB） |
| 元数据格式 | JSONL | Parquet |
| 逐集统计量 | 独立的 `episodes_stats.jsonl` | 嵌入 episodes parquet 的 `stats/*` 列 |

转换工具：`src/lerobot/datasets/v30/convert_dataset_v21_to_v30.py`
