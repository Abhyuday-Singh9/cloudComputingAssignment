.PHONY: help up down train test lint

help:
	@echo "Available commands:"
	@echo "  make up          - Build and deploy the entire system (cluster, storage, app)"
	@echo "  make down        - Tear down the cluster and clean up resources"
	@echo "  make train       - Run student model training (use SUBSET=N to train on N samples)"
	@echo "  make test        - Run unit tests"
	@echo "  make lint        - Run lint checks"

train:
	python training/train.py --config training/config.yaml $(if $(SUBSET),--subset $(SUBSET),)

test:
	python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
	python -m pytest tests/

lint:
	python -m flake8 service/ tests/ tools/

up:
	kubectl apply -f k8s/namespaces.yaml
	kubectl apply -f k8s/seaweedfs.yaml
	kubectl apply -f k8s/service.yaml

down:
	k3d cluster delete cloud-cluster || true

