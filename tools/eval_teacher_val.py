import json
import requests
import time

def main():
    with open('prompts/teacher_prompt.txt', 'r', encoding='utf-8') as f:
        system_prompt = f.read().strip()

    val_records = []
    with open('data/validation.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                val_records.append(json.loads(line))

    print(f"Loaded {len(val_records)} validation records. Running evaluation on teacher (phi3.5)...")
    
    predictions = []
    start_time = time.time()
    
    for i, record in enumerate(val_records):
        rec_id = record['id']
        text = record['text']
        full_prompt = f"{system_prompt}\n\nCommand: {text}\nJSON:"
        
        try:
            resp = requests.post('http://localhost:11434/api/generate', json={
                'model': 'phi3.5',
                'prompt': full_prompt,
                'stream': False,
                'options': {
                    'temperature': 0,
                    'seed': 42
                }
            }, timeout=60)
            
            raw_reply = resp.json().get('response', '').strip()
        except Exception as e:
            print(f"Error on {rec_id}: {e}")
            raw_reply = ""
            
        predictions.append({"id": rec_id, "prediction": raw_reply})
        if (i + 1) % 10 == 0 or (i + 1) == len(val_records):
            elapsed = time.time() - start_time
            print(f"Processed {i + 1}/{len(val_records)} in {elapsed:.1f}s ({(elapsed/(i+1)):.2f}s/req)")
            
    with open('results/teacher_preds.jsonl', 'w', encoding='utf-8') as f:
        for pred in predictions:
            f.write(json.dumps(pred) + '\n')
            
    print("Saved predictions to results/teacher_preds.jsonl")

if __name__ == '__main__':
    main()

