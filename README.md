# Cloud Computing Mini Project: Knowledge Distillation & Deployment

**Course:** CS3081 — Cloud Computing  
**Student Name:** Abhyuday Singh  
**Roll Number:** 230101042  
**GitHub Repository:** [https://github.com/Abhyuday-Singh9/cloudComputingAssignment](https://github.com/Abhyuday-Singh9/cloudComputingAssignment)  
**Model Release Asset:** [https://github.com/Abhyuday-Singh9/cloudComputingAssignment/releases/tag/v1.0.0](https://github.com/Abhyuday-Singh9/cloudComputingAssignment/releases/tag/v1.0.0)  

---

## Overview

This project demonstrates sequence-level knowledge distillation (Seq-KD) of a natural language command parser from a 3.8B parameter teacher model (`phi3.5`) to an ultra-lightweight 70M parameter student model (`EleutherAI/pythia-70m`). The distilled model is deployed as a cloud-native microservice on a local Kubernetes (`k3d`) cluster with SeaweedFS S3 object storage, health probes, automated horizontal autoscaling (HPA), stateless network access controls (NACL), and an automated 4-stage GitHub Actions CI/CD pipeline.

---

## Project Structure

```
├── .github/workflows/   # CI/CD pipeline (gitleaks, lint, unit tests, score quality gate)
├── cluster/             # Declarative k3d cluster configuration (cluster/k3d.yaml)
├── data/                # Datasets (commands pool, validation set, schema, rate card)
├── datasets/            # Cleaned training dataset and reproducible SHA-256 checksum
├── k8s/                 # Kubernetes manifests (namespaces, seaweedfs, service, HPA, ingress)
├── models/              # Release archive model-v1.zip, sha256 checksum (weights excluded from Git)
├── network/             # Subnetting scheme (network/subnets.md) and stateless NACL (network/nacl.json)
├── prompts/             # Teacher prompt specification (prompts/teacher_prompt.txt)
├── report/              # Final 8-page PDF report (report/report.pdf) and notes
├── results/             # Evaluation scores, Locust load test metrics, evidence logs
├── service/             # FastAPI inference microservice and CPU-optimized Dockerfile
├── tests/               # PyTest unit test suite (7 tests)
├── tools/               # Evaluation, simulation, and load-testing utilities
├── training/            # PyTorch / HuggingFace training script, config, and loss log
├── worker/              # Parallel teacher-labelling workers and dataset cleaning pipeline
├── AI_USE.md            # Mandatory academic AI usage record
├── Makefile             # Root orchestration targets (up, down, train, test, lint)
└── README.md            # Setup, deployment, testing, and operations guide
```

---

## Instructions: Build, Deploy, Test & Shutdown

All operations are fully orchestrated via the root `Makefile` and standard CLI tools (`kubectl`, `k3d`, `docker`, `locust`).

### 1. Build & Deploy (`make up`)
Bootstraps the local cluster, provisions object storage, and deploys the 2-replica service:
```bash
# 1. Create cluster from cluster/k3d.yaml (1 server, 1 agent, port 8080:80)
k3d cluster create --config cluster/k3d.yaml

# 2. Deploy namespaces, SeaweedFS S3 storage, and inference service
make up
```
*Verification:*
```bash
kubectl get pods -A
curl http://127.0.0.1:8080/healthz
curl -X POST http://127.0.0.1:8080/parse -H "Content-Type: application/json" -d "{\"text\":\"set alarm for 7 am\"}"
```

### 2. Run Student Training (`make train`)
Fine-tunes `EleutherAI/pythia-70m` on CPU using the cleaned teacher outputs:
```bash
# Smoke test on a subset of 50 samples
make train SUBSET=50

# Full training run across all 1,497 cleaned records
make train
```
Training loss is logged per epoch to `training/loss.csv`. Model checkpoints are saved in `models/v1/`.

### 3. Run Automated Tests and Linters (`make test`, `make lint`)
```bash
# Run unit tests (7 tests) and stateless firewall packet simulation (6 tests)
make test

# Run Flake8 style and syntax enforcement
make lint
```

### 4. Run Headless Load Testing (Locust)
Executes a 60-second concurrent load test against the Traefik Ingress:
```bash
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 1m --host http://127.0.0.1:8080 --csv results/loadtest
```
Metrics are recorded to `results/loadtest_stats.csv` and replica headers to `results/loadtest_headers.json`.

### 5. Tear Down & Shutdown (`make down`)
Deletes the local k3d cluster and cleans up all running containers:
```bash
make down
```

---

## Key Results Summary

* **Student Model Performance**: **98.0% JSON validity**, **73.0% intent accuracy**, **38.0% full-frame accuracy** on `data/validation.jsonl` (retaining 90.5% of teacher full-frame accuracy).
* **Container Optimization**: Image size is **343 MB** (CPU-only PyTorch wheels; no model weights in image).
* **Cgroup Resource Profiling**: 50 requests under 1 CPU and 1 GiB RAM completed with **623.4 MiB peak memory** and **0 OOM kills**.
* **Zero-Downtime Rolling Update**: Transition from model `v1` to `v2` completed with **0 dropped requests (0.0% error rate)**.
* **Cold-Start Latency**: Measured median cold-start time of **56.0 seconds** over 3 empirical runs.
* **Cost Estimation**: **₹5.91 per 1,000 requests** modeled via `data/rate_card.json`.
* **Security & Cleanliness**: **0 Gitleaks secrets detected**; Flake8 linting reports **0 errors**.
