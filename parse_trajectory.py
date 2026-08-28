# parse_trajectory.py — Robust ETL utility for verification and dataset formatting
import os
import sys
import json
import re
import subprocess

# Pinning variables
REPO_NAME = "arrow-py/arrow"
BASE_COMMIT = "2224255c4acc594d734cef0bbc83360452a67983"
DOCKER_IMAGE_DIGEST = "sha256:d710c57be5da884f3ddb7f81b51179d146371c61e3af6447f3e6a0ce54b2483c"
PYTHON_VERSION = "3.11.16"

def load_task_spec(task_dir: str):
    """Parses details from TASK.md."""
    task_md_path = os.path.join(task_dir, "TASK.md")
    if not os.path.exists(task_md_path):
        raise FileNotFoundError(f"Cannot find TASK.md at {task_md_path}")
        
    content = open(task_md_path, "r", encoding="utf-8").read()
    
    # Extract commit hash
    commit_match = re.search(r"Base repo: arrow-py/arrow @ ([a-f0-9]+)", content)
    commit = commit_match.group(1) if commit_match else "unknown"
    
    # Extract Problem statement
    problem_match = re.search(r"## Problem statement.*?## Success criteria", content, re.DOTALL)
    problem = ""
    if problem_match:
        problem = problem_match.group(0).replace("## Problem statement (what the model will see)", "").replace("## Success criteria", "").strip()
        
    # Extract Gold Diff
    gold_match = re.search(r"## Hidden gold fix.*?Diff:\s*```diff\s*(.*?)\s*```", content, re.DOTALL)
    gold_diff = gold_match.group(1) if gold_match else ""
    
    # Extract Gold Files changed
    files_match = re.search(r"-\s*File\(s\)\s*changed:\s*([^\s\n\r]+)", content)
    gold_files = set()
    if files_match:
        gold_files.add(files_match.group(1).strip("`\"'"))
    
    return commit, problem, gold_diff, gold_files

def run_verifier(container_tag: str, workspace_dir: str) -> dict:
    """Runs the test suite inside the sandbox and parses the REAL output.
    This is the only place reward is allowed to be computed."""
    norm_workspace = os.path.abspath(workspace_dir).replace("\\", "/")
    
    result = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{norm_workspace}:/workspace",
         container_tag, "-c", "cd /workspace && pytest tests/ -q --tb=short --no-cov"],
        capture_output=True, text=True, timeout=120,
    )
    raw_output = result.stdout + result.stderr

    # Parse pytest's summary line: e.g. "3 failed, 41 passed in 2.11s" or "1904 passed in 0.50s"
    m = re.search(r"(?:(\d+) failed, )?(\d+) passed", raw_output)
    if not m:
        return {
            "tests_passed": 0,
            "tests_total": 0,
            "reward": 0.0,
            "raw_output": raw_output,
            "collection_error": True,
        }
        
    failed = int(m.group(1) or 0)
    passed = int(m.group(2))
    total = failed + passed
    return {
        "tests_passed": passed,
        "tests_total": total,
        "reward": round(passed / total, 4) if total else 0.0,
        "raw_output": raw_output,
        "collection_error": False,
    }

def classify(fail_to_pass_now_passes: bool, pass_to_pass_all_still_pass: bool,
             trajectory: list, edited_files: set, gold_files: set) -> str | None:
    """The ONLY function allowed to set failure_category. Called after run_verifier()."""
    if fail_to_pass_now_passes and pass_to_pass_all_still_pass:
        return None  # genuinely solved — no failure category
        
    if not pass_to_pass_all_still_pass:
        return "regression_introduced"  # broke something that used to work
        
    if not fail_to_pass_now_passes:
        # Check if they verified by running pytest in the last 2 steps
        ran_tests_before_declaring_done = False
        last_two = trajectory[-2:] if len(trajectory) >= 2 else trajectory
        for step in last_two:
            if step["action"] == "run_command" and "pytest" in step.get("cmd", ""):
                ran_tests_before_declaring_done = True
                
        if not ran_tests_before_declaring_done:
            return "didnt_verify"
            
        if not edited_files:
            return "misdiagnosis"
            
        # If edits landed completely outside of any file mentioned in gold_files
        if edited_files.isdisjoint(gold_files):
            return "misdiagnosis"
            
        return "incomplete_fix"
        
    return None

def validate_row(row: dict) -> None:
    """Ensures row values are internally consistent and validate requirements."""
    r = row["verifier_result"]
    
    if r["fail_to_pass"] and r["pass_to_pass"] and row["failure_category"] is not None:
        raise ValueError(f"{row['task_id']}: fully passing run cannot have a failure_category")
        
    if row["reward"] == 1.0 and row["failure_category"] is not None:
        raise ValueError(f"{row['task_id']}: reward=1.0 cannot coexist with a failure_category")
        
    if row["reward"] < 1.0 and row["failure_category"] is None:
        raise ValueError(f"{row['task_id']}: failing run must have a failure_category")
        
    if not (0.0 <= row["reward"] <= 1.0):
        raise ValueError(f"{row['task_id']}: reward out of range")

def append_run(row: dict, path="dataset/runs.jsonl"):
    """Validates the record first, then appends it to the dataset."""
    validate_row(row)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")

def parse_run(task_id: str, run_dir: str, target_repo_dir: str, model_name: str, wall_clock_seconds: int = 120):
    """ETL parser execution flow with double-run verification."""
    task_spec_dir = os.path.join(target_repo_dir, "tasks", task_id)
    commit, instruction, gold_diff, gold_files = load_task_spec(task_spec_dir)
    
    trajectory_path = os.path.join(run_dir, "trajectory.json")
    if os.path.exists(trajectory_path):
        full_trajectory = json.load(open(trajectory_path, "r"))
    else:
        full_trajectory = []
        
    final_diff_path = os.path.join(run_dir, "final_diff.patch")
    final_diff = ""
    if os.path.exists(final_diff_path):
        final_diff = open(final_diff_path, "r", encoding="utf-8").read()

    # Track edited files from trajectory
    edited_files = set()
    for step in full_trajectory:
        if step["action"] == "edit_file":
            edited_files.add(step["target"])
            
    # 1. Run verifier on base buggy code (pre-patch)
    print(f"[*] Running baseline verifier (buggy state) for {task_id}...")
    # Make sure repo is clean of patches first
    subprocess.run(["git", "checkout", "."], cwd=target_repo_dir, capture_output=True)
    buggy_out = run_verifier("taskforge-arrow", target_repo_dir)
    
    # 2. Apply patch and run verifier on patched code (post-patch)
    if final_diff.strip():
        print(f"[*] Applying agent patch for {task_id}...")
        # Apply the patch using git apply
        patch_path = os.path.abspath(final_diff_path)
        subprocess.run(["git", "apply", "--ignore-whitespace", patch_path], cwd=target_repo_dir, capture_output=True)
        
        print(f"[*] Running verifier on patched state for {task_id}...")
        patched_out = run_verifier("taskforge-arrow", target_repo_dir)
        
        # Clean up the patch from the repo
        subprocess.run(["git", "checkout", "."], cwd=target_repo_dir, capture_output=True)
    else:
        print(f"[*] No patch to apply for {task_id}.")
        patched_out = buggy_out

    # Save raw pytest output to file
    raw_output_dir = os.path.join("runs", f"{task_id}_{model_name}")
    os.makedirs(raw_output_dir, exist_ok=True)
    raw_output_file = os.path.join(raw_output_dir, "raw_output.txt")
    with open(raw_output_file, "w", encoding="utf-8") as f:
        f.write(patched_out["raw_output"])
        
    # Evaluate verifier parameters
    regression_test_name = f"test_regression_{task_id.split('-')[-1]}"
    
    # Check if the regression test passed in the patched run
    fail_to_pass_now_passes = regression_test_name not in patched_out["raw_output"] and not patched_out["collection_error"]
    
    # Check if there are any new test failures introduced by the patch
    pass_to_pass_all_still_pass = True
    if patched_out["collection_error"]:
        pass_to_pass_all_still_pass = False
    elif patched_out["tests_passed"] < buggy_out["tests_passed"]:
        # The number of passed tests in the patched run is lower than the buggy run
        # Wait, if the regression test passes, it increases the passed count by 1.
        # But if we also broke other tests, the total passed count might decrease.
        # More precisely, a regression was introduced if any test that was passing in the buggy run now fails.
        pass_to_pass_all_still_pass = False
    
    # Calculate failure category
    failure_category = classify(
        fail_to_pass_now_passes=fail_to_pass_now_passes,
        pass_to_pass_all_still_pass=pass_to_pass_all_still_pass,
        trajectory=full_trajectory,
        edited_files=edited_files,
        gold_files=gold_files
    )
    
    # Environment ref pinning
    environment_ref = {
        "repo": REPO_NAME,
        "base_commit": BASE_COMMIT,
        "docker_image_digest": DOCKER_IMAGE_DIGEST,
        "python_version": PYTHON_VERSION
    }
    
    record = {
        "task_id": task_id,
        "environment_ref": environment_ref,
        "instruction": instruction,
        "gold_diff": gold_diff,
        "model_name": model_name,
        "full_trajectory": full_trajectory,
        "final_diff": final_diff,
        "verifier_result": {
            "pass_to_pass": pass_to_pass_all_still_pass,
            "fail_to_pass": fail_to_pass_now_passes,
            "tests_passed": patched_out["tests_passed"],
            "tests_total": patched_out["tests_total"],
            "raw_output_path": raw_output_file.replace("\\", "/")
        },
        "reward": patched_out["reward"],
        "failure_category": failure_category,
        "iterations_used": len(full_trajectory),
        "wall_clock_seconds": wall_clock_seconds
    }
    
    append_run(record)
    print(f"[+] Loaded run for {task_id} successfully (reward={patched_out['reward']}, category={failure_category})")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python parse_trajectory.py <task_id> <run_dir> <target_repo_dir> <model_name> [wall_clock_seconds]")
        sys.exit(1)
        
    t_id = sys.argv[1]
    r_dir = sys.argv[2]
    repo_dir = sys.argv[3]
    m_name = sys.argv[4]
    wall_clock = int(sys.argv[5]) if len(sys.argv) > 5 else 120
    
    parse_run(t_id, r_dir, repo_dir, m_name, wall_clock)
