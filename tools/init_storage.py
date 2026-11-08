import os
import boto3
from botocore.client import Config


def init_s3():
    endpoint_url = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333")
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "cloudadmin")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "cloudsecret123")

    s3 = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        config=Config(signature_version='s3v4'),
        region_name='us-east-1'
    )

    # 1. Create buckets
    required_buckets = ['datasets', 'models']

    for b in required_buckets:
        try:
            s3.create_bucket(Bucket=b)
            print(f"Created bucket: {b}")
        except Exception as e:
            print(f"Bucket {b} already exists or error: {e}")

    # 2. Upload commands_pool.jsonl
    pool_path = "data/commands_pool.jsonl"
    if os.path.exists(pool_path):
        print(f"Uploading {pool_path} to s3://datasets/commands_pool.jsonl ...")
        s3.upload_file(pool_path, "datasets", "commands_pool.jsonl")
        print("Upload successful!")
    else:
        print(f"Error: {pool_path} not found.")

    # 3. Verify
    resp = s3.list_objects_v2(Bucket="datasets")
    keys = [item['Key'] for item in resp.get('Contents', [])]
    print(f"Objects in 'datasets' bucket: {keys}")


if __name__ == '__main__':
    init_s3()
