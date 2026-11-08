import os
import sys
import json
import time
import requests
import boto3
from botocore.client import Config


def get_s3_client():
    s3_endpoint = os.environ.get("S3_ENDPOINT", "http://seaweedfs.data.svc.cluster.local:8333")
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "cloudadmin")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "cloudsecret123")

    return boto3.client(
        's3',
        endpoint_url=s3_endpoint,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )


def load_prompt():
    prompt_path = os.environ.get("PROMPT_PATH", "teacher_prompt.txt")
    if not os.path.exists(prompt_path):
        prompt_path = "prompts/teacher_prompt.txt"
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def main():
    shard_index_str = os.environ.get("SHARD_INDEX")
    shard_count_str = os.environ.get("SHARD_COUNT")

    if shard_index_str is None or shard_count_str is None:
        sys.exit("Error: SHARD_INDEX and SHARD_COUNT environment variables are required.")

    shard_index = int(shard_index_str)
    shard_count = int(shard_count_str)
    ollama_host = os.environ.get("OLLAMA_HOST", "http://host.k3d.internal:11434")

    print(f"Starting Shard Worker: SHARD_INDEX={shard_index}, SHARD_COUNT={shard_count}")
    print(f"Ollama Endpoint: {ollama_host}")

    s3 = get_s3_client()
    system_prompt = load_prompt()

    # 1. Download commands_pool.jsonl from S3
    local_pool_file = "/tmp/commands_pool.jsonl"
    os.makedirs("/tmp", exist_ok=True)

    try:
        s3.download_file("datasets", "commands_pool.jsonl", local_pool_file)
        print("Downloaded commands_pool.jsonl from datasets bucket.")
    except Exception as e:
        # Fallback to local if running outside cluster
        if os.path.exists("data/commands_pool.jsonl"):
            local_pool_file = "data/commands_pool.jsonl"
            print("Using local data/commands_pool.jsonl.")
        else:
            raise e

    # 2. Read all commands
    all_commands = []
    with open(local_pool_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_commands.append(json.loads(line))

    # 3. Filter for this shard: index % SHARD_COUNT == SHARD_INDEX
    shard_commands = [
        cmd for i, cmd in enumerate(all_commands)
        if i % shard_count == shard_index
    ]

    shard_s3_key = f"teacher/shard-{shard_index}.jsonl"
    local_shard_file = f"/tmp/shard-{shard_index}.jsonl"

    # 4. Check for existing progress in S3 to resume
    processed_ids = set()
    try:
        s3.download_file("datasets", shard_s3_key, local_shard_file)
        with open(local_shard_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    processed_ids.add(item["id"])
        print(f"Resuming shard {shard_index}: found {len(processed_ids)} already processed records in S3.")
    except Exception:
        print("No prior shard file found in S3. Starting fresh.")
        if os.path.exists(local_shard_file):
            os.remove(local_shard_file)

    print(f"Total commands assigned to this shard: {len(shard_commands)} (already processed: {len(processed_ids)})")

    # 5. Process remaining commands
    with open(local_shard_file, "a", encoding="utf-8") as out_f:
        for cmd in shard_commands:
            cmd_id = cmd["id"]
            if cmd_id in processed_ids:
                continue

            text = cmd["text"]
            # Call Ollama API
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

            teacher_raw = ""
            for attempt in range(3):
                try:
                    resp = requests.post(f"{ollama_host}/api/generate", json=payload, timeout=120)
                    if resp.status_code == 200:
                        teacher_raw = resp.json().get("response", "").strip()
                        break
                    else:
                        print(f"HTTP {resp.status_code} from Ollama on attempt {attempt + 1}, retrying...")
                        time.sleep(2)
                except Exception as ex:
                    print(f"Error querying Ollama on attempt {attempt + 1}: {ex}")
                    time.sleep(3)

            record = {
                "id": cmd_id,
                "text": text,
                "teacher_raw": teacher_raw
            }
            out_f.write(json.dumps(record) + "\n")
            out_f.flush()
            processed_ids.add(cmd_id)

            # Periodically sync to S3 every 10 commands
            if len(processed_ids) % 10 == 0 or len(processed_ids) == len(shard_commands):
                s3.upload_file(local_shard_file, "datasets", shard_s3_key)
                print(f"Progress [{shard_index}]: {len(processed_ids)}/{len(shard_commands)} uploaded to S3.")

    # Final upload
    s3.upload_file(local_shard_file, "datasets", shard_s3_key)
    print(f"Shard {shard_index} completed successfully! Uploaded to s3://datasets/{shard_s3_key}")


if __name__ == "__main__":
    main()
