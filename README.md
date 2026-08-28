# TaskForge — Agentic Coding Task Authoring & Model Audit

TaskForge is a sandbox environment and automated pipeline for authoring, injecting, and auditing frontier AI agents on software engineering tasks. Built on top of the date/time handling library `arrow-py/arrow`, TaskForge mirrors the SWE-bench benchmark paradigm by presenting realistic, calibrated bugs to an agent, executing its output inside a sandboxed Docker container, and transforming the run trajectories into a failure taxonomy dataset.

---

## 🛠️ Architecture Overview

The system consists of the following components:
1. **Target Sandbox (`arrow-py/arrow`)**: A clone of a clean date/time utility library containing injected bugs mapped to isolated git branches.
2. **Task Specifications (`tasks/`)**: Structuring of environment definitions, issue descriptions (symptoms only), success criteria, and hidden gold fixes.
3. **Docker Sandbox (`docker/`)**: Offline, secure, containerized execution environment for testing agent outputs.
4. **Agent Harness (`simple_agent_loop.py`)**: A lightweight script to run arbitrary model queries inside the docker container in an agentic loop.
5. **ETL Parser (`parse_trajectory.py`)**: A utility that parses model trajectories, runs verifications, computes rewards, and appends to a pandas-ready dataset.
6. **Dataset Schema (`dataset/runs.jsonl`)**: Structured, append-only logs capturing environmental refs, trajectories, rewards, and failure taxonomies.

```
                  ┌───────────────────────┐
                  │      Agent / CLI      │
                  └───────────┬───────────┘
                              │ Sends commands
                              ▼
┌──────────────────────────────────────────────────────────┐
│                   TaskForge Workspace                    │
│                                                          │
│  ┌───────────────────────┐       ┌────────────────────┐  │
│  │   simple_agent_loop   ├──────►│   Docker Sandbox   │  │
│  └───────────────────────┘       │ (taskforge-arrow)  │  │
│                                  └─────────┬──────────┘  │
│                                            │ Runs tests  │
│                                            ▼             │
│  ┌───────────────────────┐       ┌────────────────────┐  │
│  │   parse_trajectory    │◄──────┤    runs.jsonl      │  │
│  └───────────────────────┘       └────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 🐞 Calibrated Bugs Directory

TaskForge defines three bugs across distinct categories:

| ID | Category | Symptom | Location | Gold Fix |
|---|---|---|---|---|
| **bug-01** | Subtle Logic / Off-By-One | `Arrow.range()` excludes the final endpoint if step exactly divides range. | `arrow/arrow.py` | Change `current < end` back to `current <= end`. |
| **bug-02** | Wrong-but-Plausible API Call | `Arrow.span()` inverts inclusion/exclusion bounds checking logic. | `arrow/arrow.py` | Check open boundaries (`(` / `)`) instead of closed (`[` / `]`). |
| **bug-03** | Multi-File Dependency Break | `Arrow.get()` silently truncates sub-second precision (microseconds/milliseconds). | `arrow/util.py` | Change `int` return type conversion to `float` in `normalize_timestamp()`. |

---

## 📊 Audited Failure Taxonomy

After evaluating Claude Code runs, we categorized failures using the standard taxonomy. Evaluated runs are logged in `dataset/runs.jsonl`:

| Task ID | Failure Category | Symptom in Trajectory | Reward | Iterations | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **bug-01** | *None* (Success) | Solved | **1.0000** | 4 steps | Successfully identified the off-by-one boundary bug and applied the correct inclusive condition. |
| **bug-02** | `regression_introduced` | Broke validation rules in `util.py` | **0.9806** | 4 steps | Attempted to change bounds validator in `util.py` which broke existing bounds validation tests. |
| **bug-03** | `misdiagnosis` | Modified `arrow.py` instead of `util.py` | **0.9969** | 4 steps | Attempted to patch the caller inside `arrow.py` instead of fixing the root cause utility in `util.py`. |

> [!TIP]
> **Audit Insight**: In agent auditing, tasks where every run scores exactly `0.0` or `1.0` carry no training signal (low-information). Genuinely valuable tasks maintain a **30%–70% pass rate** over repeated runs, highlighting subtle boundary checks or multi-file dependencies.

---

## 🚀 Execution & Sandbox Instructions

### 1. Prerequisite Setup
Ensure python virtual environment is initialized and dependencies installed:
```bash
cd taskforge-target
python -m venv .venv
.\.venv\Scripts\activate
pip install -e .[test]
```

### 2. Sandbox Verification via Docker
Make sure Docker Desktop is running, then build and verify:
```bash
# Build sandbox image
docker build -t taskforge-arrow -f docker/Dockerfile .

# Run test script inside container (fails on buggy commit)
docker run --rm taskforge-arrow -c "bash docker/run_tests.sh"
```

To verify a gold patch solves the issue:
```bash
# Checkout target branch
git checkout bug/01-offbyone

# Run container applying the gold patch at runtime
docker run --rm -v $(pwd)/gold/01.patch:/patch.diff taskforge-arrow \
  -c "git apply /patch.diff && bash docker/run_tests.sh"
```

### 3. Parse and Populate Dataset
Run the ETL parser to ingest new trajectories:
```bash
python parse_trajectory.py <task_id> <run_dir> <target_repo_dir> <model_name> [wall_clock_seconds]
```
Example:
```bash
python parse_trajectory.py bug-01 runs/bug-01_claude-code taskforge-target claude-code 187
```
This appends a new record to `dataset/runs.jsonl`.

### 4. Replay and Verify Trajectories
To verify reproducibility of logged agent runs:
```bash
python replay.py <task_id> <run_dir>
```
Example:
```bash
python replay.py bug-01 runs/bug-01_claude-code
```
This clones a fresh repository copy, checks out the appropriate bug branch, applies the patch, executes tests inside the Docker sandbox, and creates a local `output.txt` for comparison with `raw_output.txt`.
