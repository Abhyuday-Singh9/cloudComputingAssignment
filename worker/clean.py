import os
import sys
import json
import hashlib
import boto3
from botocore.client import Config

ALLOWED_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events"
}

ALLOWED_KEYS = {"intent", "date", "time", "place"}


def get_s3_client():
    s3_endpoint = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333")
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


def compute_sha256(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    s3 = get_s3_client()
    local_shards_dir = "worker/shards"
    os.makedirs(local_shards_dir, exist_ok=True)
    os.makedirs("datasets/v1", exist_ok=True)

    print("Fetching teacher shard files from S3...")
    all_raw_records = []

    # List shards from S3 datasets bucket
    try:
        resp = s3.list_objects_v2(Bucket="datasets", Prefix="teacher/shard-")
        shard_keys = [obj["Key"] for obj in resp.get("Contents", []) if obj["Key"].endswith(".jsonl")]
        print(f"Found {len(shard_keys)} shard objects in S3: {shard_keys}")
    except Exception as e:
        print(f"Could not list S3 objects: {e}. Checking local {local_shards_dir}...")
        shard_keys = []

    if shard_keys:
        for key in sorted(shard_keys):
            local_file = os.path.join(local_shards_dir, os.path.basename(key))
            print(f"Downloading {key} -> {local_file}")
            s3.download_file("datasets", key, local_file)
            with open(local_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        all_raw_records.append(json.loads(line))
    else:
        # Check local directory
        for fname in sorted(os.listdir(local_shards_dir)):
            if fname.endswith(".jsonl"):
                with open(os.path.join(local_shards_dir, fname), "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            all_raw_records.append(json.loads(line))

    total_input = len(all_raw_records)
    print(f"Loaded {total_input} total raw records from teacher shards.")

    if total_input == 0:
        print("No teacher records found to clean yet. Exiting.")
        sys.exit(0)

    # Sort all raw records by id first to ensure determinism and for rule (e) smallest id
    all_raw_records.sort(key=lambda r: r["id"])

    # Track rejections in strict sequential order:
    # (a) not valid JSON
    # (b) keys not exactly intent, date, time, place
    # (c) intent not one of the eight
    # (d) a slot value that is neither null nor a string appearing in the command text
    # (e) duplicate commands (keep the smallest id)
    count_a = 0  # not valid JSON
    count_b = 0  # invalid keys
    count_c = 0  # invalid intent
    count_d = 0  # invalid slot value
    count_e = 0  # duplicate commands
    kept_records = []

    seen_command_texts = set()

    for rec in all_raw_records:
        rec_id = rec["id"]
        text = rec["text"]
        raw = rec.get("teacher_raw", "").strip()

        # Check (a): not valid JSON
        try:
            parsed = json.loads(raw)
        except Exception:
            count_a += 1
            continue

        if not isinstance(parsed, dict):
            count_a += 1
            continue

        # Check (b): keys not exactly intent, date, time, place
        if set(parsed.keys()) != ALLOWED_KEYS:
            count_b += 1
            continue

        # Check (c): intent not one of the eight
        if parsed.get("intent") not in ALLOWED_INTENTS:
            count_c += 1
            continue

        # Check (d): slot value neither null nor string appearing in command text
        slot_invalid = False
        for slot in ("date", "time", "place"):
            val = parsed.get(slot)
            if val is not None:
                if not isinstance(val, str) or val.strip().lower() not in text.strip().lower():
                    slot_invalid = True
                    break
        if slot_invalid:
            count_d += 1
            continue

        # Check (e): duplicate commands (keep smallest id)
        norm_text = text.strip().lower()
        if norm_text in seen_command_texts:
            count_e += 1
            continue

        seen_command_texts.add(norm_text)
        kept_records.append({
            "id": rec_id,
            "text": text,
            "intent": parsed["intent"],
            "date": parsed["date"],
            "time": parsed["time"],
            "place": parsed["place"]
        })

    count_kept = len(kept_records)

    # Verify counts balance equation
    sum_parts = count_a + count_b + count_c + count_d + count_e + count_kept
    assert sum_parts == total_input, f"Counts equation mismatch: {sum_parts} != {total_input}"

    print("\n--- Data Cleaning Counts Summary ---")
    print(f"Total Input Records:      {total_input}")
    print(f"(a) Not Valid JSON:       {count_a}")
    print(f"(b) Invalid Keys:         {count_b}")
    print(f"(c) Invalid Intent:       {count_c}")
    print(f"(d) Invalid Slot Value:   {count_d}")
    print(f"(e) Duplicate Commands:   {count_e}")
    print(f"Kept Valid Records:       {count_kept}")
    print(f"Balance Verification:     {count_a} + {count_b} + {count_c} + {count_d} + {count_e} + {count_kept} = {sum_parts} (Matches Input)")

    # Sort kept records by ID
    kept_records.sort(key=lambda r: r["id"])

    # Write datasets/v1/train.jsonl
    train_path = "datasets/v1/train.jsonl"
    with open(train_path, "w", encoding="utf-8", newline="\n") as f:
        for item in kept_records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    sha256_hash = compute_sha256(train_path)
    sha_path = "datasets/v1/train.sha256"
    with open(sha_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{sha256_hash}  train.jsonl\n")

    print(f"\nWritten {count_kept} records to {train_path}")
    print(f"SHA256: {sha256_hash} (written to {sha_path})")

    # Upload to S3 datasets bucket
    try:
        s3.upload_file(train_path, "datasets", "v1/train.jsonl")
        s3.upload_file(sha_path, "datasets", "v1/train.sha256")
        print("Uploaded train.jsonl and train.sha256 to s3://datasets/v1/")
    except Exception as e:
        print(f"Note: Could not upload to S3: {e}")


if __name__ == "__main__":
    main()
