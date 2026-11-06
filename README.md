# Cloud Computing Mini Project: Knowledge Distillation & Deployment

This project demonstrates sequence-level knowledge distillation of a natural language command parser from a teacher model (`phi3.5`) to a lightweight student model (`EleutherAI/pythia-70m`), deployed on a local k3d Kubernetes cluster with object storage, automated health checks, autoscaling (HPA), and CI/CD quality gating.

## Project Structure

```
├── .github/workflows/   # CI/CD pipeline definitions
├── cluster/             # Cluster configuration (k3d.yaml)
├── data/                # Datasets (commands pool, validation set, schemas, rate card)
├── k8s/                 # Kubernetes manifests (namespaces, deployments, services, ingress, HPA)
├── network/             # Network design: subnetting plan and NACL rules
├── prompts/             # Teacher prompt specification
├── report/              # Final PDF report and notes
├── results/             # Evaluation scores, Locust load test metrics, evidence
├── service/             # FastAPI inference web service container
├── tests/               # Unit and integration test suites
├── tools/               # Evaluation, simulation, and load-testing utilities
├── training/            # PyTorch / HuggingFace fine-tuning scripts and loss logs
├── worker/              # Parallel teacher-labelling workers and dataset cleaning pipeline
├── AI_USE.md            # Mandatory log of AI usage and verification
├── Makefile             # Orchestration targets (up, down, train, test, lint)
└── README.md            # Setup and operations guide
```

## Quick Start & Operations

### 1. Build and Deploy (`make up`)
Builds container images, bootstraps the local k3d cluster, sets up SeaweedFS object storage, creates required buckets, uploads datasets, and deploys the inference service.
```bash
make up
```

### 2. Run Student Training
Fine-tune Pythia-70M on teacher-generated outputs:
```bash
# Test run on a subset (50 samples)
make train SUBSET=50

# Full training run
make train
```

### 3. Run Tests and Linters
```bash
make test
make lint
```

### 4. Tear Down Cluster (`make down`)
```bash
make down
```

