# AGENTS.md

## Project

LeRobot — Hugging Face's robotics library. Python 3.10+, PyTorch-based, single-package layout at `src/lerobot/`. Config uses **draccus** (not argparse/hydra). CLI entry points are `lerobot-train`, `lerobot-eval`, etc. (defined in `pyproject.toml [project.scripts]`).

## Install

```bash
# Dev install (editable, from repo root)
pip install -e ".[dev,test]"

# With a specific robot/policy extra
pip install -e ".[feetech,smolvla]"

# uv alternative (used in CI)
uv sync --extra "test"        # fast tests only
uv sync --extra all            # all extras (includes flash-attn, hardware SDKs)
```

Some extras conflict (e.g. `wallx` pins `transformers==4.49.0`); see `[tool.uv] conflicts` in `pyproject.toml`.

## Lint & Format

Ruff is the linter+formatter. Pre-commit runs ruff, mypy, typos, pyupgrade, bandit, gitleaks, prettier (markdown).

```bash
pre-commit run --all-files          # run all hooks
pre-commit run ruff --all-files     # lint only
pre-commit run ruff-format --all-files  # format only
```

Ruff config: line-length=110, target py310. `T201` (print) is ignored — `print()` is allowed. Docstring convention is Google style.

## Type Checking

```bash
mypy --config-file=pyproject.toml src/lerobot
```

Mypy is incremental: only `lerobot.envs`, `lerobot.configs`, `lerobot.optim`, `lerobot.model`, `lerobot.cameras`, `lerobot.transport` have `ignore_errors = false`. The rest of `lerobot.*` currently has `ignore_errors = true`.

## Tests

```bash
# Full suite
pytest tests -vv --maxfail=10

# Single test file
pytest -sv tests/datasets/test_le_robot_dataset.py

# Single test by name
pytest -sv tests/policies/test_policies.py -k "test_forward"

# End-to-end training+eval (requires simulation extras)
make test-end-to-end               # all E2E tests
make test-act-ete-train            # single E2E training run
make DEVICE=cpu test-act-ete-train # force CPU
```

Test device defaults to `cuda` if available, else `cpu`. Override with `LEROBOT_TEST_DEVICE=cpu`.

Many tests skip when hardware (cameras, motors) or optional packages (gym-aloha, etc.) are not available. `git lfs pull` is required for test artifacts under `tests/artifacts/`.

CI fast tests run on every PR (`tests -vv --maxfail=10` with `--extra test`). Full tests + E2E run after PR approval.

## Architecture

```
src/lerobot/
  configs/     — draccus dataclass configs (train.py, eval.py, types.py)
  scripts/     — CLI entry points (lerobot_train.py, lerobot_eval.py, ...)
  policies/    — policy implementations (act, diffusion, tdmpc, vqbet, smolvla, pi, groot, ...)
  datasets/    — LeRobotDataset, data loading, video decoding
  robots/      — hardware robot abstractions
  cameras/     — camera backends (opencv, intelrealsense)
  motors/      — motor SDKs (dynamixel, feetech)
  teleoperators/ — teleoperation devices
  envs/        — simulation environment wrappers
  optim/       — optimizers, schedulers
  model/       — shared model components
  processor/   — data processing pipelines
  rl/          — reinforcement learning (actor-learner, SAC)
  transport/   — gRPC transport layer
  async_inference/ — async inference server
  utils/       — shared utilities
```

## Conventions

- Config-driven: training/eval scripts take `--key.subkey=value` args parsed by draccus. No YAML config files to edit.
- When adding a new policy: update `available_policies` and `available_policies_per_env` in `src/lerobot/__init__.py`, and add tests to `tests/test_available.py`.
- When adding a new env/dataset: update `available_tasks_per_env` and `available_datasets_per_env` in `src/lerobot/__init__.py`.
- `tests/fixtures/` provides shared pytest fixtures (dataset_factories, hub, files, optimizers) registered as plugins in `conftest.py`.
- `HF_LEROBOT_HOME` env var controls the local cache directory (defaults to `~/.cache/huggingface/lerobot`). Test artifacts go to `HF_LEROBOT_HOME/_testing`.
