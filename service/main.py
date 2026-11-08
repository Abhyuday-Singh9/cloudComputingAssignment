import os
import json
import socket
import logging
import threading
from typing import Optional, Dict, Any

from fastapi import FastAPI, Response, status
from pydantic import BaseModel
import boto3
from botocore.client import Config

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inference_service")

app = FastAPI(title="Command Parser Inference Service")

# Configuration from environment variables
MODEL_URI = os.environ.get("MODEL_URI", "s3://models/v1")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs.data.svc.cluster.local:8333")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "64"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0")
POD_NAME = os.environ.get("HOSTNAME", socket.gethostname())

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

# Global model state
MODEL = None
TOKENIZER = None
MODEL_READY = False
LOAD_LOCK = threading.Lock()


class ParseRequest(BaseModel):
    text: str


def download_s3_directory(s3_uri: str, local_dir: str):
    """Downloads model files from s3://bucket/prefix into local_dir."""
    uri_parts = s3_uri.replace("s3://", "").split("/", 1)
    bucket = uri_parts[0]
    prefix = uri_parts[1] if len(uri_parts) > 1 else ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    logger.info(f"Downloading model from bucket='{bucket}', prefix='{prefix}' to '{local_dir}'...")
    os.makedirs(local_dir, exist_ok=True)

    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID", "cloudadmin")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "cloudsecret123")

    s3 = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"
    )

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel_path = key[len(prefix):] if key.startswith(prefix) else os.path.basename(key)
            if not rel_path:
                continue
            dest_file = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            logger.info(f"Downloading {key} -> {dest_file}")
            s3.download_file(bucket, key, dest_file)
    logger.info("Download from S3 completed.")


def init_model():
    """Background loader for model and tokenizer."""
    global MODEL, TOKENIZER, MODEL_READY
    with LOAD_LOCK:
        try:
            local_dir = "/tmp/model"
            if MODEL_URI.startswith("s3://"):
                download_s3_directory(MODEL_URI, local_dir)
            else:
                local_dir = MODEL_URI

            logger.info("Loading tokenizer and model with PyTorch/Transformers...")
            from transformers import AutoTokenizer, AutoModelForCausalLM
            import torch

            TOKENIZER = AutoTokenizer.from_pretrained(local_dir)
            if TOKENIZER.pad_token is None:
                TOKENIZER.pad_token = TOKENIZER.eos_token

            MODEL = AutoModelForCausalLM.from_pretrained(
                local_dir,
                torch_dtype=torch.float32
            )
            MODEL.eval()
            MODEL_READY = True
            logger.info("Model loaded successfully and marked READY.")
        except Exception as e:
            logger.error(f"Error loading model from {MODEL_URI}: {e}")
            # If model weights are not yet trained/available, stay not ready
            MODEL_READY = False


@app.on_event("startup")
def on_startup():
    threading.Thread(target=init_model, daemon=True).start()


@app.get("/healthz")
def healthz():
    return {"status": "alive"}


@app.get("/readyz")
def readyz(response: Response):
    if not MODEL_READY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "loading"}
    return {"status": "ready"}


def validate_output(output_str: str) -> Optional[Dict[str, Any]]:
    """Checks output against schema.json. Returns parsed dict if valid, else None."""
    try:
        data = json.loads(output_str)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    if set(data.keys()) != ALLOWED_KEYS:
        return None

    if data.get("intent") not in ALLOWED_INTENTS:
        return None

    for slot in ("date", "time", "place"):
        val = data.get(slot)
        if val is not None and not isinstance(val, str):
            return None

    return data


@app.post("/parse")
def parse(req: ParseRequest, response: Response):
    # Set required headers on all responses
    response.headers["X-Model-Version"] = os.environ.get("MODEL_VERSION", MODEL_VERSION)
    response.headers["X-Served-By"] = POD_NAME

    if not MODEL_READY or MODEL is None or TOKENIZER is None:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"error": "model_not_ready"}

    prompt = f"Command: {req.text}\nJSON:"
    inputs = TOKENIZER(prompt, return_tensors="pt")

    try:
        import torch
        with torch.no_grad():
            outputs = MODEL.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                pad_token_id=getattr(TOKENIZER, "pad_token_id", 0),
                eos_token_id=getattr(TOKENIZER, "eos_token_id", 0)
            )
    except Exception:
        outputs = MODEL.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS)

    # Decode only the generated tokens after the prompt
    input_ids = inputs["input_ids"]
    input_length = input_ids.shape[1] if hasattr(input_ids, "shape") else len(input_ids[0])
    gen_tokens = outputs[0][input_length:]
    generated_text = TOKENIZER.decode(gen_tokens, skip_special_tokens=True).strip()

    # Extract first line or until newline
    if "\n" in generated_text:
        generated_text = generated_text.split("\n", 1)[0].strip()

    # Fault injection: replace model output with "not json"
    fault_inject = os.environ.get("FAULT_INJECT", FAULT_INJECT)
    if fault_inject == "1":
        generated_text = "not json"

    # Validate against schema
    validated = validate_output(generated_text)
    if validated is None:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"error": "invalid_model_output"}

    # Success: HTTP 200 with only the 4-key JSON body
    return validated
