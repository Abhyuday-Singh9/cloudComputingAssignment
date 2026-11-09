# AI Use Record

This file documents AI tool assistance utilized during the project in accordance with course guidelines.

| Date | Tool / Model | Purpose / Task | How Verified |
| :--- | :--- | :--- | :--- |
| 2026-11-06 | Coding Assistant | Command-line syntax lookup and local tooling configuration reference (k3d, kubectl, Locust, Gitleaks) | Tested tool version and help commands directly in PowerShell; verified zero secrets found with `gitleaks detect` |
| 2026-11-06 | Coding Assistant | Clarifying concepts in knowledge distillation literature (Kim & Rush 2016 vs. logit-based distillation) | Cross-referenced with the Kim & Rush paper (Sections 1–3) and PyTorch Knowledge Distillation tutorial |
| 2026-11-07 | Coding Assistant | Verifying IPv4 CIDR subnetting host arithmetic formulas and stateless NACL rule evaluation ordering | Calculated host boundaries manually ($2^{32-\text{prefix}} - 2$) and verified rule decisions using `tools/nacl_sim.py` |
| 2026-11-08 | Coding Assistant | Documentation lookup for PyTorch CPU `float32` optimization and dynamic batch collation syntax | Verified execution and numerical convergence locally via `make train SUBSET=50` and PyTest unit test suite |
| 2026-11-08 | Coding Assistant | YAML syntax reference for GitHub Actions `needs:` job dependency sequencing and `workflow_dispatch` inputs | Validated pipeline execution order and quality gate threshold checks directly in GitHub Actions |
