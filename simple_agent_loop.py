# simple_agent_loop.py — Minimal comparison harness for running agent loops in the sandbox
import os
import subprocess
import sys

# Get current workspace directory in absolute form (using forward slashes for docker compat)
PWD = os.path.abspath(os.getcwd()).replace("\\", "/")

def run_in_sandbox(cmd: str) -> str:
    """Executes a command inside the taskforge-arrow Docker sandbox container."""
    try:
        # Run inside container mounting workspace as /workspace
        result = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{PWD}/taskforge-target:/workspace", "taskforge-arrow", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 60 seconds."
    except Exception as e:
        return f"ERROR executing command: {str(e)}"

def agent_loop(model_client, task_prompt: str, max_steps: int = 15):
    """Simple loop that presents a task to a model client and executes returned shell commands."""
    history = [{"role": "user", "content": task_prompt}]
    print(f"[*] Starting agent loop for task. Max steps: {max_steps}")
    
    for step in range(max_steps):
        print(f"\n[Step {step + 1}/{max_steps}] Requesting next command from model...")
        response = model_client.send(history)
        action = response.strip()
        print(f"[Model Action]: {action}")
        
        if action == "DONE" or "DONE" in action:
            print("[*] Model signaled DONE. Terminating loop.")
            break
            
        print(f"[*] Running command in sandbox: {action}")
        output = run_in_sandbox(action)
        print(f"[Sandbox Output]:\n{output}")
        
        history.append({"role": "assistant", "content": action})
        history.append({"role": "user", "content": f"Output:\n{output}"})
        
    return history

if __name__ == "__main__":
    # Example usage: python simple_agent_loop.py "pytest tests/regression_test_01.py"
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        print(f"Running query in sandbox: {cmd}")
        print(run_in_sandbox(cmd))
    else:
        print("Usage: python simple_agent_loop.py [command]")
