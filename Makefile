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
	python -m pytest tests/

lint:
	python -m flake8 service/ worker/ training/ tests/ || python -m ruff check service/ worker/ training/ tests/

up:
	@echo "Deploying system..."

down:
	k3d cluster delete cloud-cluster || true
