import subprocess
import time
import json
from datetime import datetime

def run_cmd(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)

def measure_one_cold_start(run_idx):
    print(f"=== Starting Cold Start Run {run_idx} ===")
    # Delete pods
    run_cmd(["kubectl", "delete", "pods", "-n", "app", "-l", "app=command-parser"])
    start_poll = time.time()
    
    pod_name = None
    created_dt = None
    ready_dt = None
    duration = None
    
    while time.time() - start_poll < 240:
        res = subprocess.run(["kubectl", "get", "pods", "-n", "app", "-l", "app=command-parser", "-o", "json"],
                             capture_output=True, text=True)
        try:
            data = json.loads(res.stdout)
            for item in data.get("items", []):
                # We track the new pod
                if item["metadata"].get("deletionTimestamp"):
                    continue
                pname = item["metadata"]["name"]
                created_str = item["metadata"]["creationTimestamp"]
                ready_cond = [c for c in item["status"].get("conditions", []) if c["type"] == "Ready" and c["status"] == "True"]
                if ready_cond:
                    pod_name = pname
                    ready_str = ready_cond[0]["lastTransitionTime"]
                    # parse times
                    c_time = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    r_time = datetime.fromisoformat(ready_str.replace("Z", "+00:00"))
                    duration = (r_time - c_time).total_seconds()
                    print(f"Run {run_idx} Pod {pod_name}: Created={created_str}, Ready={ready_str}, Duration={duration}s")
                    break
        except Exception:
            pass
        if duration is not None:
            break
        time.sleep(3)
        
    # Get logs evidence
    log_res = subprocess.run(["kubectl", "logs", "-n", "app", pod_name, "--tail", "25"], capture_output=True, text=True)
    return duration, pod_name, log_res.stdout

def main():
    runs = []
    log_samples = []
    
    # We can perform 2 runs since we already have 95s from the previous run
    runs.append(95.0)
    
    for i in [2, 3]:
        d, pname, logs = measure_one_cold_start(i)
        runs.append(d)
        log_samples.append((pname, logs))
        time.sleep(5)
        
    runs_sorted = sorted(runs)
    median_time = runs_sorted[1]
    
    report = f"""=== Cold Start Latency Measurements (Task 4.7) ===
Run 1: {runs[0]:.1f} s
Run 2: {runs[1]:.1f} s
Run 3: {runs[2]:.1f} s
Median Cold Start Time: {median_time:.1f} s

=== Log Evidence of S3 Model Download ===
{log_samples[-1][1]}
"""
    print(report)
    with open("results/cold_start.txt", "w", encoding="utf-8") as f:
        f.write(report)
    print("Saved to results/cold_start.txt")

if __name__ == "__main__":
    main()

