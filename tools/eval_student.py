import argparse
import json
import os
import subprocess
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Pythia model on validation set.")
    parser.add_argument("--model-path", required=True, help="Path to model and tokenizer")
    parser.add_argument("--data-path", default="data/validation.jsonl", help="Validation dataset path")
    parser.add_argument("--preds-out", required=True, help="Path to write predictions JSONL")
    parser.add_argument("--report-out", required=True, help="Path to write score report JSON")
    parser.add_argument("--max-new-tokens", type=int, default=64, help="Max tokens to generate")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(os.path.dirname(args.preds_out) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(args.report_out) or ".", exist_ok=True)

    print(f"Loading model and tokenizer from {args.model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(args.model_path)
    model.eval()

    val_records = []
    with open(args.data_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                val_records.append(json.loads(line))

    print(f"Loaded {len(val_records)} validation records. Running greedy inference...")

    predictions = []
    start_time = time.time()

    for i, record in enumerate(val_records):
        rec_id = record["id"]
        cmd_text = record["text"]
        prompt = f"Command: {cmd_text}\nJSON:"

        inputs = tokenizer(prompt, return_tensors="pt")
        input_length = inputs["input_ids"].shape[1]

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id
            )

        gen_tokens = outputs[0][input_length:]
        gen_text = tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()

        # Stop at first newline
        if "\n" in gen_text:
            gen_text = gen_text.split("\n", 1)[0].strip()

        predictions.append({
            "id": rec_id,
            "prediction": gen_text
        })

    elapsed = time.time() - start_time
    print(f"Inference complete on {len(val_records)} records in {elapsed:.2f}s ({(elapsed / len(val_records)):.4f}s/req)")

    # Save predictions
    with open(args.preds_out, "w", encoding="utf-8", newline="\n") as f:
        for p in predictions:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Saved predictions to {args.preds_out}")

    # Score predictions
    cmd = ["python", "tools/score.py", args.preds_out, args.data_path, "--out", args.report_out]
    print(f"Scoring: {' '.join(cmd)}")
    subprocess.run(cmd, check=False)
    print(f"Score report written to {args.report_out}")


if __name__ == "__main__":
    main()
