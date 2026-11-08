import json
import os
import subprocess
import time
import requests


def main():
    os.makedirs("results", exist_ok=True)

    prompt_path = "prompts/teacher_prompt.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()

    val_records = []
    with open("data/validation.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                val_records.append(json.loads(line))

    print(f"Loaded {len(val_records)} validation records. Running evaluation on teacher (phi3.5)...")

    predictions = []
    start_time = time.time()

    for i, record in enumerate(val_records):
        rec_id = record["id"]
        text = record["text"]

        payload = {
            "model": "phi3.5:latest",
            "prompt": f"Command: {text}\nJSON:",
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_predict": 64,
                "stop": ["\n"]
            }
        }

        raw_reply = ""
        try:
            resp = requests.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=60)
            if resp.status_code == 200:
                raw_reply = resp.json().get("response", "").strip()
        except Exception as e:
            print(f"Error on {rec_id}: {e}")

        predictions.append({"id": rec_id, "prediction": raw_reply})
        if (i + 1) % 10 == 0 or (i + 1) == len(val_records):
            elapsed = time.time() - start_time
            print(f"Processed {i + 1}/{len(val_records)} in {elapsed:.1f}s ({(elapsed / (i + 1)):.2f}s/req)")

    pred_path = "results/teacher_preds.jsonl"
    with open(pred_path, "w", encoding="utf-8") as f:
        for pred in predictions:
            f.write(json.dumps(pred) + "\n")

    print(f"Saved predictions to {pred_path}")

    # Run score.py
    report_path = "results/teacher_validation.json"
    cmd = ["python", "tools/score.py", pred_path, "data/validation.jsonl", "--out", report_path]
    print(f"Scoring with: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"Teacher validation score report written to {report_path}")


if __name__ == "__main__":
    main()
