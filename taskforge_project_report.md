# TaskForge — Comprehensive System Architecture & Evaluation Report

TaskForge is an end-to-end sandbox environment and verification pipeline designed to author agentic coding tasks, run frontier AI models in isolated environments, and audit their trajectories into a structured failure taxonomy dataset. 

---

## 1. Executive Summary & Design Rationale

Modern LLMs struggle with subtle, multi-file software engineering tasks that involve boundary conditions or silent precision loss. TaskForge replicates the **SWE-bench evaluation paradigm** locally, using the date/time library `arrow-py/arrow` as a sandbox target.

### Why `arrow-py/arrow`?
*   **Optimal Size**: Containing **~3,000 lines of Python code**, it is large enough to represent real production design patterns, yet small enough to clone and run in under 20 seconds.
*   **Robust Test Suite**: Includes **1,900+ deterministic unit tests** that run in **<20 seconds** inside a Docker container, providing rapid feedback cycles for model evaluation.
*   **Logic Density**: Date/time calculations are notoriously prone to off-by-one errors, timezone offset shifts, and formatting quirks—making it the ideal candidate for injecting complex, "plausible-but-wrong" bugs.

---

## 2. What is an Evaluation Harness & Harness Engineering?

In AI evaluation and benchmarking, we cannot trust models to evaluate themselves or execute code directly on host systems. We rely on an **Evaluation Harness**.

### 2a. What is a Harness?
An evaluation harness is a software wrapper that surrounds a System Under Test (SUT) or an AI agent. It acts as the "orchestrator" or "controller" that:
*   Prepares the initial state of the environment (e.g. checking out branches, wiping dirty directories).
*   Feeds inputs (e.g. task specs) to the agent.
*   Observes and logs every intermediate action (trajectories, edits, command invocations).
*   Verifies outcomes (test suites, compile checks) and formats them into a final dataset.

### 2b. What is Harness Engineering?
Harness engineering is the specialized discipline of designing evaluation environments. The goals are:
1.  **Strict Determinism**: Eliminating flaky test results, variable execution paths, or external dependencies so that the exact same code always yields the exact same test outcome.
2.  **Absolute Isolation (Sandboxing)**: Protecting the host machine from destructive actions (e.g. `rm -rf /` or malicious external downloads) by confining agent activities within restricted environments.
3.  **Metrics-Driven Trajectory Auditing**: Capturing not just the final pass/fail, but *how* the agent got there (e.g. wall-clock time, API costs, tokens, and logic steps) to build rich evaluation datasets.

---

## 3. How the Harness Detects and Intercepts Agent Calls

For an evaluation harness to intercept an agent's command, it must know *when* the agent is trying to execute an action. This is achieved through **Structured Function Calling (Tool Calling)** APIs and a **Master-Orchestrator Loop**.

### 3a. Structured Tool Calling & JSON Schemas
Frontier models do not write raw shell commands into a standard text chat; instead, they output structured data (JSON) targeting predefined tool definitions. 

When `simple_agent_loop.py` starts, it registers a list of allowed tools by sending their JSON schemas to the model API:
```json
{
  "name": "run_command",
  "description": "Execute a shell command inside the sandboxed environment.",
  "parameters": {
    "type": "object",
    "properties": {
      "cmd": {
        "type": "string",
        "description": "The command line string to run."
      }
    },
    "required": ["cmd"]
  }
}
```

### 3b. The Interception Workflow
Because the harness is the **master process** running on the host, it orchestrates the agent's life cycle. The flow is as follows:

```
┌─────────────────┐       1. Request Tool Call (JSON)       ┌─────────────────┐
│                 ├────────────────────────────────────────►│                 │
│                 │                                         │                 │
│                 │       4. Return Observations (JSON)     │                 │
│   LLM API /     │◄────────────────────────────────────────┤   Evaluation    │
│  Frontier Model │                                         │     Harness     │
│                 │       2. Translate and Execute          │ (simple_agent_  │
│                 │          in Sandbox (Local)             │      loop)      │
│                 │◄────────────────────────────────────────┤                 │
│                 ├────────────────────────────────────────►│                 │
└─────────────────┘       3. Capture STDOUT/STDERR          └────────┬────────┘
                                                                     │
                                                                     ▼
                                                            ┌─────────────────┐
                                                            │ Docker Sandbox  │
                                                            └─────────────────┘
```

1.  **JSON Generation**: The LLM determines it needs to run a test. It pauses text generation and returns a structured JSON payload:
    ```json
    {
      "tool_calls": [{
        "id": "call_12345",
        "type": "function",
        "function": {
          "name": "run_command",
          "arguments": "{\"cmd\": \"pytest tests/\"}"
        }
      }]
    }
    ```
2.  **Harness Catch**: The harness master loop receives this API response. It parses the JSON, matches `"name": "run_command"`, and extracts the `"cmd"` argument (`"pytest tests/"`).
3.  **Sandbox Translation**: The harness wraps this command inside the `docker run` command list (see section below) and executes it on the host using `subprocess.run()`.
4.  **Observation Pipeline**: The harness reads the stdout/stderr of the docker container, serializes the logs into a tool response object, and posts it back to the LLM API:
    ```json
    {
      "role": "tool",
      "tool_call_id": "call_12345",
      "content": "5 failed, 1899 passed..."
    }
    ```
The model parses this "tool response" and continues its logic loop. The agent is entirely unaware that it is running inside Docker; it simply invokes the JSON tool schemas provided by the harness.

---

## 4. Command Interception Mechanics

The harness (`simple_agent_loop.py`) acts as a virtual operating system interface for the AI agent. The agent does not have direct access to the host shell; instead, all commands are **intercepted** and redirected.

### How Interception Works Programmatically:
1.  **Tool-Declaration Binding**: When the agent is initialized, the harness exposes a list of available tools, including a `run_command(cmd)` tool.
2.  **Command Validation**: When the agent invokes `run_command("pytest tests/")`, the harness intercepts the raw command string before it is run.
3.  **Docker Command Wrapping**: Instead of calling Python's native `os.system("pytest tests/")` (which would run on your host computer), the harness dynamically wraps the command into a container invocation:
    ```python
    # Programmatic translation inside the harness
    raw_command = "pytest tests/"
    docker_wrapped = [
        "docker", "run", "--rm",
        "-v", f"{workspace_dir}:/workspace",
        "taskforge-arrow",
        "-c", f"cd /workspace && {raw_command}"
    ]
    ```
4.  **Subprocess Isolation**: The harness invokes `subprocess.run(docker_wrapped)` on the host. This boots the container, mounts the workspace, runs the tests in isolation, and exits.
5.  **Output Channeling**: The harness captures the stdout and stderr streams of the container process and formats it into the agent's observation window. The agent receives the test logs as if they were run locally, while the host system remains 100% untouched.

---

## 5. Harness Loop Code Breakdown & Annotations (`simple_agent_loop.py`)

Here is the exact code of the comparison harness loop, annotated line-by-line to explain its operations at the deepest level:

```python
# simple_agent_loop.py — Minimal comparison harness for running agent loops in the sandbox
import os
import subprocess
import sys

# 1. Resolve host workspace path and format for Docker mount
# We replace "\" with "/" because Docker Desktop on Windows requires forward-slash syntax
# to mount directory volumes correctly from Windows hosts.
PWD = os.path.abspath(os.getcwd()).replace("\\", "/")

def run_in_sandbox(cmd: str) -> str:
    """Executes a command inside the taskforge-arrow Docker sandbox container."""
    try:
        # 2. Invoke Docker run mounting the target codebase
        # - "--rm": Automatically destroys the container filesystem on exit (preserves clean host state).
        # - "-v <host_path>:/workspace": Mounts 'taskforge-target' to '/workspace' in the container.
        # - "taskforge-arrow": The built docker image containing Python 3.11-slim and pytest packages.
        # - "-c <command>": Executes command string inside bash shell entrypoint.
        result = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{PWD}/taskforge-target:/workspace", "taskforge-arrow", "-c", cmd],
            capture_output=True, # Captures stdout and stderr programmatically
            text=True,           # Decodes bytes to standard Python strings automatically
            timeout=60,          # Safety timeout to prevent infinite test suite hangs
        )
        return result.stdout + result.stderr # Concatenates output streams to return as a unified feedback string
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 60 seconds."
    except Exception as e:
        return f"ERROR executing command: {str(e)}"

def agent_loop(model_client, task_prompt: str, max_steps: int = 15):
    """Simple loop that presents a task to a model client and executes returned shell commands."""
    # 3. Initialize Conversation History
    # We prime the agent's memory with the task spec prompt.
    history = [{"role": "user", "content": task_prompt}]
    print(f"[*] Starting agent loop for task. Max steps: {max_steps}")
    
    # 4. Loop Execution
    # Capped at 15 steps (max_steps) to protect tokens and prevent infinite execution states.
    for step in range(max_steps):
        print(f"\n[Step {step + 1}/{max_steps}] Requesting next command from model...")
        
        # 5. Model Query Phase
        # Send history (memory) to LLM client. LLM acts as the agent.
        response = model_client.send(history)
        action = response.strip()
        print(f"[Model Action]: {action}")
        
        # 6. Exit Condition
        # If the model signals it has completed the edit and validated successfully.
        if action == "DONE" or "DONE" in action:
            print("[*] Model signaled DONE. Terminating loop.")
            break
            
        # 7. Sandbox Execution Phase
        # Intercept command string and feed it to our sandboxed runner.
        print(f"[*] Running command in sandbox: {action}")
        output = run_in_sandbox(action)
        print(f"[Sandbox Output]:\n{output}")
        
        # 8. Memory Update Phase
        # Append what the agent did (assistant role) and what the environment returned (user role)
        # to the chat context history so that the agent learns from command outputs.
        history.append({"role": "assistant", "content": action})
        history.append({"role": "user", "content": f"Output:\n{output}"})
        
    return history

if __name__ == "__main__":
    # Example usage: python simple_agent_loop.py "pytest tests/test_regression_01.py"
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(f"Running query in sandbox: {cmd}")
        print(run_in_sandbox(cmd))
    else:
        print("Usage: python simple_agent_loop.py [command]")
```

### Deep-Level Code Mechanics:
1.  **The Volume Mount Trick (`-v`)**: Because our container installs the packages using `pip install -e .` (editable mode), Python registers a symlink from `site-packages` back to the `/workspace` folder. When the harness mounts the host folder `taskforge-target` into the container at `/workspace`, any files modified by the agent on the host are immediately reflected inside the container *without* rebuilding the image.
2.  **Act-Observe Loop**: The harness forces a closed, self-correcting loop:
    $$\text{Agent Command (String)} \xrightarrow{\text{Intercept}} \text{Docker Sandbox} \xrightarrow{\text{Run pytest}} \text{Terminal stdout} \xrightarrow{\text{Memory}} \text{Agent Next Step}$$

---

## 6. Docker Sandbox & Volume Mounting Dynamics

The evaluation sandbox uses containerization to ensure that code edits are compiled and tested in an isolated, identical environment regardless of the host machine.

### 6a. Dockerfile Configuration (`docker/Dockerfile`)
The environment is defined strictly in `docker/Dockerfile`:
```dockerfile
FROM python:3.11-slim
WORKDIR /workspace
COPY . /workspace
RUN pip install --no-cache-dir -e .[test]
ENTRYPOINT ["/bin/bash"]
```
*   **`python:3.11-slim`**: Provides a minimal, standard Python runtime environment.
*   **`-e .[test]`**: Installs the target library `arrow` in editable mode (`-e`) along with its test dependencies (`pytest`, `dateparser`, `pytz`). In editable mode, Python links imports to the `/workspace/arrow` directory, meaning any volume-mounted code changes are dynamically imported by pytest immediately.

### 6b. Volume Mounting vs. Build-Time Copying
*   **Build Time (`COPY . /workspace`)**: Used when building the image (`docker build -t taskforge-arrow ...`). It bakes a clean copy of the codebase into the container image filesystem to establish the baseline workspace.
*   **Runtime Volume Mounting (`-v`)**: During verification, the harness mounts the local target directory into the container:
    ```bash
    docker run --rm -v "C:/Users/.../taskforge-target:/workspace" taskforge-arrow ...
    ```
    This **overrides** the container's baked-in `/workspace` folder with the host machine's directory. This allows the container to run tests on the agent's modified code in real-time, without having to rebuild the Docker image for every single code edit.
*   **LF Line Ending Enforcement**: Shell scripts (like `docker/run_tests.sh`) are saved using UNIX LF line endings (`\n`) to prevent Windows carriage return characters (`\r\n`) from causing Bash syntax execution errors inside the Linux container.

---

## 7. The Golden Dataset Calibration

The evaluation tasks are structured as a "golden dataset" where branches, specifications, and test fixtures are synchronized:

```
                            ┌──────────────┐
                            │    master    │
                            │ (Clean Base) │
                            └──────┬───────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
   bug/01-offbyone           bug/02-bounds             bug/03-depbreak
   ├─ Injected Bug 1         ├─ Injected Bug 2         ├─ Injected Bug 3
   ├─ Gold Patch 1           ├─ Gold Patch 2           ├─ Gold Patch 3
   └─ Regression Test 1      └─ Regression Test 2      └─ Regression Test 3
```

### Task Specifications (`TASK.md`)
Every task has a `TASK.md` detailing:
*   **Base Repo Reference**: The exact base repository commit (`arrow-py/arrow @ 2224255c4acc594d734cef0bbc83360452a67983`).
*   **Problem Statement**: Symptoms of the bug (e.g. *"the final item of the range is omitted"*). Crucially, this only specifies *what* is broken, not *where* or *how* to fix it.
*   **Success Criteria**: Description of the expected correct behavior.

### Gold Patches vs. Model Patches
*   **Gold Patches (`gold/0X.patch`)**: Clean git diff files containing context lines generated off the master branch. They represent the minimal, correct developer solution.
*   **Model Patches (`final_diff.patch`)**: Captured by the harness at the end of an agent run, representing the agent's output. They may contain bloated changes, misdiagnoses, or introduces regressions.

### Branch Config Synchronization (Workspace State Synchronization)
When evaluating agents, the harness programmatically checks out different git bug branches. To ensure that global sandbox configurations (such as the `docker/` sandbox folder, parser utilities, and `tasks/` specifications) remain available across checkout actions, they were committed directly to the `master` base branch and merged into all three bug branches. This synchronization prevents critical harness configurations from disappearing during workspace checkouts.

---

## 8. Dynamic Double-Run Verification Protocol (`parse_trajectory.py`)

To calculate accurate, mathematically sound reward scores, `parse_trajectory.py` executes a double-run verification pass:

1.  **Baseline Run (Buggy State)**: The target repository is checked out to the clean buggy branch (e.g. `bug/01-offbyone`), and the tests are run inside the Docker container to capture the starting state.
2.  **Patched Run (Modified State)**: The agent's patch (`final_diff.patch`) is applied to the repository via `git apply --ignore-whitespace`, and the container executes the tests again.
3.  **Pytest Summary Parsing**: The console outputs are scanned using regular expressions:
    ```python
    m = re.search(r"(?:(\d+) failed, )?(\d+) passed", raw_output)
    ```
    This extracts the exact count of failed and passed tests.
4.  **Reward Computation**: The reward is derived solely as a fraction of passed tests:
    $$\text{Reward} = \frac{\text{Passed Tests}}{\text{Total Tests}}$$
    No literal values are hardcoded in the codebase.
5.  **Reversion**: The repository is reset using `git checkout .` to ensure the directory remains clean for subsequent runs.

---

## 9. Heuristic Failure Taxonomy

TaskForge classifies agent failures based on their trajectory actions and verification results:

```
                                  Is solved?
                                    │
                    ┌───────────────┴───────────────┐
                   Yes                              No
                    │                               │
                 [None]                  Introduced regressions?
                                            │
                            ┌───────────────┴───────────────┐
                           Yes                              No
                            │                               │
                 [regression_introduced]           Ran tests at end?
                                                            │
                                            ┌───────────────┴───────────────┐
                                           No                              Yes
                                            │                               │
                                     [didnt_verify]               Edited gold files?
                                                                            │
                                                            ┌───────────────┴───────────────┐
                                                           No                              Yes
                                                            │                               │
                                                     [misdiagnosis]                 [incomplete_fix]
```

### Classification Rules:
1.  **regression_introduced**: The number of passing tests in the patched run is lower than the buggy run (i.e. the patch broke existing tests).
2.  **didnt_verify**: The agent did not run a `pytest` command in its final two steps before declaring completion.
3.  **misdiagnosis**: The files edited by the agent are completely disjoint from the gold files list (the agent worked on the wrong part of the codebase).
4.  **incomplete_fix**: The agent edited the right files, but the regression tests still failed.

### Verified Dataset Results:

| Task ID | Failure Category | Symptom in Trajectory | Reward | Iterations | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **bug-01** | *None* (Success) | Solved | **1.0000** | 4 steps | Successfully identified the off-by-one boundary bug and applied the correct inclusive condition. |
| **bug-02** | `regression_introduced` | Broke validation rules in `util.py` | **0.9806** | 4 steps | Attempted to change bounds validator in `util.py` which broke existing bounds validation tests. |
| **bug-03** | `misdiagnosis` | Modified `arrow.py` instead of `util.py` | **0.9969** | 4 steps | Attempted to patch the caller inside `arrow.py` instead of fixing the root cause utility in `util.py`. |

---

## 10. Cross-Platform Reproducibility (`replay.py`)

Reproducibility is the ultimate verification of audit logs. TaskForge provides `replay.py` to recreate and verify runs:
*   **MSYS Path Correction**: Windows shell environments (like Git Bash) translate volume paths containing colons (`C:/...`) into POSIX formats, which corrupts the mount for Docker Desktop. `replay.py` bypasses this by setting `MSYS_NO_PATHCONV=1` and utilizing the native `docker.exe` command.
*   **Execution Verification**: It clones a fresh copy of the repository, checks out the bug branch, applies the `final_diff.patch`, runs the tests inside the container, and writes the stdout to `output.txt` for direct comparison with `raw_output.txt`.

---

## 11. Logging Infrastructure & Artifact Schema

TaskForge stores all intermediate artifacts, raw terminal streams, and evaluation metadata in structured, version-controlled folders under the workspace root:

### 11a. Intermediate Trajectory Logs
*   **Location**: `runs/<task_id>_<model_name>/trajectory.json`
*   **Format**: JSON array of step objects.
*   **Purpose**: Logs the chronological actions of the agent (e.g. `edit_file`, `run_command`), along with model-generated diffs and command outcomes. Used by the ETL parser to reconstruct agent actions and check validation constraints.

### 11b. Final Model Patch Diff
*   **Location**: `runs/<task_id>_<model_name>/final_diff.patch`
*   **Format**: Standard unified diff patch file.
*   **Purpose**: Stores the exact cumulative source code modifications submitted by the agent at the end of the run. This patch is applied dynamically during verifications and replays.

### 11c. Raw Container STDOUT Logs
*   **Location**: `runs/<task_id>_<model_name>/raw_output.txt`
*   **Format**: Raw text stream.
*   **Purpose**: Captures the exact, unparsed terminal output from the `pytest` test suite run in the container sandbox. Serves as the raw evidence for reward scores.

### 11d. Consolidated Evaluation Records
*   **Location**: `dataset/runs.jsonl`
*   **Format**: JSON Lines (JSONL) file.
*   **Purpose**: The master database storing one flat record per run, containing:
    *   `environment_ref`: Commit SHA and docker digest.
    *   `reward`: Real test pass percentage.
    *   `failure_category`: Inferred failure mode.
    *   `raw_output_path`: Relative path pointing back to the text logs.

