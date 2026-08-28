# replay.py — Reproducibility verification tool
import os
import sys
import shutil
import subprocess

def run_replay(task_id: str, run_dir: str):
    if task_id == "bug-01":
        branch = "bug/01-offbyone"
    elif task_id == "bug-02":
        branch = "bug/02-bounds"
    elif task_id == "bug-03":
        branch = "bug/03-depbreak"
    else:
        print(f"Unknown task_id: {task_id}")
        sys.exit(1)

    replay_dir = f"temp_replay_{task_id}"
    if os.path.exists(replay_dir):
        shutil.rmtree(replay_dir)

    print(f"[*] Cloning fresh repository copy for {task_id}...")
    subprocess.run(["git", "clone", "taskforge-target", replay_dir], check=True)

    try:
        # Switch to branch
        print(f"[*] Checking out branch {branch}...")
        subprocess.run(["git", "checkout", branch], cwd=replay_dir, check=True)
        subprocess.run(["git", "checkout", "arrow/"], cwd=replay_dir, check=True)

        # Apply agent's patch
        patch_file = os.path.abspath(os.path.join(run_dir, "final_diff.patch"))
        if os.path.exists(patch_file) and os.path.getsize(patch_file) > 0:
            print(f"[*] Applying agent patch: {patch_file}...")
            subprocess.run(["git", "apply", "--ignore-whitespace", patch_file], cwd=replay_dir, check=True)
        else:
            print("[*] No patch to apply, running in buggy state.")

        # Resolve host path for Docker
        abs_replay_dir = os.path.abspath(replay_dir).replace("\\", "/")
        print(f"[*] Running verification tests in Docker sandbox...")
        
        # Run pytest inside container mounting the temp replay directory
        result = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{abs_replay_dir}:/workspace",
             "taskforge-arrow", "-c", "cd /workspace && pytest tests/ -q --tb=short --no-cov"],
            capture_output=True, text=True
        )
        
        output_txt = result.stdout + result.stderr
        print("\n=== TEST OUTPUT ===")
        print(output_txt)
        
        # Save output for comparison
        out_file = os.path.join(replay_dir, "output.txt")
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(output_txt)

        raw_ref_file = os.path.join(run_dir, "raw_output.txt")
        print("\n--------------------------------------------------------")
        print(f"Compare {out_file} against {raw_ref_file}")
        print("They must match.")
        print("--------------------------------------------------------")

    finally:
        # Clean up
        print("[*] Cleaning up temporary replay directory...")
        if os.path.exists(replay_dir):
            shutil.rmtree(replay_dir)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python replay.py <task_id> <run_dir>")
        print("Example: python replay.py bug-01 runs/bug-01_claude-code")
        sys.exit(1)
        
    run_replay(sys.argv[1], sys.argv[2])
