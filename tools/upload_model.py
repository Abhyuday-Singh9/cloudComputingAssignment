import os
import sys
import hashlib
import zipfile
import argparse
import boto3
from botocore.client import Config
from boto3.s3.transfer import TransferConfig


def parse_args():
    parser = argparse.ArgumentParser(description="Upload model directory to SeaweedFS S3 and generate archive.")
    parser.add_argument("--model-dir", required=True, help="Path to local model directory")
    parser.add_argument("--version", required=True, help="Model version, e.g. v1, v2")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8333", help="S3 endpoint")
    return parser.parse_args()


def compute_sha256(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def main():
    args = parse_args()
    model_dir = args.model_dir
    version = args.version
    s3_endpoint = args.endpoint

    if not os.path.isdir(model_dir):
        sys.exit(f"Directory {model_dir} does not exist.")

    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "cloudadmin"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "cloudsecret123"),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"
    )

    # 1. Create reproducible zip archive for GitHub Release & checksum
    os.makedirs("models", exist_ok=True)
    archive_path = f"models/model-{version}.zip"
    print(f"Creating release archive {archive_path}...")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in sorted(os.listdir(model_dir)):
            full_path = os.path.join(model_dir, fname)
            if os.path.isfile(full_path):
                zf.write(full_path, arcname=fname)

    archive_sha = compute_sha256(archive_path)
    sha_path = f"models/{version}_model.sha256"
    with open(sha_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"{archive_sha}  model-{version}.zip\n")

    print(f"Archive SHA-256: {archive_sha} (saved to {sha_path})")

    # 2. Upload individual files to s3://models/<version>/
    t_config = TransferConfig(
        multipart_threshold=250 * 1024 * 1024,
        max_concurrency=1,
        use_threads=False
    )
    print(f"Uploading model files from {model_dir} to s3://models/{version}/...")
    for fname in sorted(os.listdir(model_dir)):
        full_path = os.path.join(model_dir, fname)
        if os.path.isfile(full_path):
            s3_key = f"{version}/{fname}"
            print(f"  Uploading {fname} -> s3://models/{s3_key}")
            s3.upload_file(full_path, "models", s3_key, Config=t_config)

    # 3. Upload archive and sha to S3 as well
    s3.upload_file(archive_path, "models", f"{version}/model-{version}.zip", Config=t_config)
    s3.upload_file(sha_path, "models", f"{version}/model.sha256", Config=t_config)
    print(f"Model version {version} upload completed successfully.")


if __name__ == "__main__":
    main()
