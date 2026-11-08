import os
import sys
import csv
import json
import time
import random
import argparse
import gc
import yaml
import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(description="Train distilled student model (Pythia-70M).")
    parser.add_argument("--config", default="training/config.yaml", help="Path to config.yaml")
    parser.add_argument("--subset", type=int, default=None, help="Subset of training records to use")
    parser.add_argument("--data-path", default="datasets/v1/train.jsonl", help="Path to train.jsonl")
    parser.add_argument("--output-dir", default="models/v1", help="Output directory for model and tokenizer")
    return parser.parse_args()


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def main():
    args = parse_args()

    # Load configuration
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    seed = config.get("seed", 42)
    learning_rate = float(config.get("learning_rate", 1e-4))
    batch_size = int(config.get("batch_size", 4))
    epochs = int(config.get("epochs", 2))
    max_seq_length = int(config.get("max_seq_length", 64))
    model_name = config.get("model_name", "EleutherAI/pythia-70m")
    mask_prompt = config.get("mask_prompt", True)
    subset = args.subset if args.subset is not None else config.get("subset")
    grad_accum_steps = int(config.get("gradient_accumulation_steps", 1))
    max_grad_norm = float(config.get("max_grad_norm", 1.0))

    set_seed(seed)

    print(f"Loaded config: seed={seed}, lr={learning_rate}, batch_size={batch_size}, "
          f"epochs={epochs}, max_len={max_seq_length}, subset={subset}, grad_accum={grad_accum_steps}", flush=True)

    # Load dataset
    data_path = args.data_path
    if not os.path.exists(data_path):
        if os.path.exists("data/validation.jsonl"):
            print(f"Warning: {data_path} not found. Using data/validation.jsonl for testing.", flush=True)
            data_path = "data/validation.jsonl"
        else:
            sys.exit(f"Dataset file {data_path} not found.")

    raw_records = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                raw_records.append(json.loads(line))

    if subset is not None:
        training_records = raw_records[:subset]
    else:
        training_records = raw_records[:1500]

    print(f"Training on {len(training_records)} records.", flush=True)

    # Import torch and transformers
    try:
        import torch
        from torch.utils.data import Dataset, DataLoader
        from transformers import AutoTokenizer, AutoModelForCausalLM
    except ImportError as e:
        sys.exit(f"PyTorch or Transformers not installed in this environment: {e}")

    # Set optimal CPU thread count
    torch.set_num_threads(4)

    # Use local untrained model if available, else HuggingFace model
    model_source = "models/untrained" if os.path.exists("models/untrained") else model_name
    print(f"Loading base model from {model_source}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_source)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_source, dtype=torch.float32)
    model = model.to(torch.float32)
    model.train()

    class DynamicCommandDataset(Dataset):
        def __init__(self, records):
            self.items = []
            for item in records:
                cmd_text = item["text"]
                reply_dict = {
                    "intent": item["intent"],
                    "date": item["date"],
                    "time": item["time"],
                    "place": item["place"]
                }
                reply_json = json.dumps(reply_dict)
                prompt = f"Command: {cmd_text}\nJSON:"
                target = f" {reply_json}{tokenizer.eos_token}"

                prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)
                target_ids = tokenizer.encode(target, add_special_tokens=False)
                full_ids = prompt_ids + target_ids

                if len(full_ids) > max_seq_length:
                    full_ids = full_ids[:max_seq_length]

                self.items.append((prompt_ids, full_ids))

        def __len__(self):
            return len(self.items)

        def __getitem__(self, idx):
            return self.items[idx]

    def collate_fn(batch):
        # Dynamic padding to batch max length
        max_batch_len = max(len(full_ids) for _, full_ids in batch)
        pad_id = tokenizer.pad_token_id

        batch_input_ids = []
        batch_attention_mask = []
        batch_labels = []

        for prompt_ids, full_ids in batch:
            seq_len = len(full_ids)
            pad_len = max_batch_len - seq_len

            input_ids = full_ids + [pad_id] * pad_len
            attention_mask = [1] * seq_len + [0] * pad_len

            # Label masking: mask prompt tokens and padding with -100
            labels = list(input_ids)
            prompt_len = min(len(prompt_ids), seq_len)
            if mask_prompt:
                for i in range(prompt_len):
                    labels[i] = -100
            for i in range(seq_len, max_batch_len):
                labels[i] = -100

            batch_input_ids.append(input_ids)
            batch_attention_mask.append(attention_mask)
            batch_labels.append(labels)

        return {
            "input_ids": torch.tensor(batch_input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(batch_attention_mask, dtype=torch.long),
            "labels": torch.tensor(batch_labels, dtype=torch.long)
        }

    dataset = DynamicCommandDataset(training_records)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, collate_fn=collate_fn)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

    os.makedirs("training", exist_ok=True)
    loss_history = []
    total_steps_per_epoch = len(dataloader)
    total_training_steps = total_steps_per_epoch * epochs

    print(f"Beginning training: {epochs} epochs, {total_steps_per_epoch} steps/epoch, "
          f"total {total_training_steps} steps.", flush=True)

    global_step = 0
    train_start_time = time.time()
    loss_csv_path = "training/loss.csv"

    # Initialize loss.csv
    with open(loss_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch", "loss"])

    for epoch in range(1, epochs + 1):
        epoch_start_time = time.time()
        total_epoch_loss = 0.0
        step_in_epoch = 0

        for batch_idx, batch in enumerate(dataloader):
            step_start = time.time()
            input_ids = batch["input_ids"]
            attention_mask = batch["attention_mask"]
            labels = batch["labels"]

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels
            )
            loss = outputs.loss
            loss_val = loss.item()

            if grad_accum_steps > 1:
                loss = loss / grad_accum_steps

            loss.backward()

            if (batch_idx + 1) % grad_accum_steps == 0 or (batch_idx + 1) == total_steps_per_epoch:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
                optimizer.step()
                optimizer.zero_grad()

            total_epoch_loss += loss_val
            step_in_epoch += 1
            global_step += 1

            step_time = time.time() - step_start
            elapsed = time.time() - train_start_time
            steps_left = total_training_steps - global_step
            est_remaining_sec = (elapsed / global_step) * steps_left

            if step_in_epoch % 10 == 0 or step_in_epoch == 1 or step_in_epoch == total_steps_per_epoch:
                print(f"[Epoch {epoch}/{epochs}] Step {step_in_epoch}/{total_steps_per_epoch} "
                      f"({int(100 * global_step / total_training_steps)}%) | "
                      f"Loss: {loss_val:.4f} | Batch: {input_ids.shape[1]} tokens | "
                      f"Step: {step_time:.1f}s | Left: {est_remaining_sec/60:.1f}m", flush=True)

        avg_epoch_loss = total_epoch_loss / max(step_in_epoch, 1)
        loss_history.append((epoch, avg_epoch_loss))
        epoch_duration = time.time() - epoch_start_time
        print(f"--> Epoch {epoch}/{epochs} Finished in {epoch_duration/60:.1f}m | "
              f"Average Loss: {avg_epoch_loss:.4f}", flush=True)

        # Write intermediate loss.csv after each epoch
        with open(loss_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["epoch", "loss"])
            for ep, l_val in loss_history:
                writer.writerow([ep, f"{l_val:.6f}"])

        gc.collect()

    total_duration = time.time() - train_start_time
    print(f"\nTraining completed in {total_duration/60:.1f}m. Loss history saved to {loss_csv_path}", flush=True)

    # Save model and tokenizer
    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)
    print(f"Saving fine-tuned model and tokenizer to {out_dir}...", flush=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"Model successfully saved to {out_dir}!", flush=True)


if __name__ == "__main__":
    main()
