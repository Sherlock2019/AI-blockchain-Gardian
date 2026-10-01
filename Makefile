.DEFAULT_GOAL := help
PY := backend/.venv/bin

.PHONY: help install demo demo-lite chain deploy backend frontend \
        test test-backend test-contracts test-chain lint build docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

install: ## Install backend, contract and dashboard dependencies
	python3 -m venv backend/.venv
	$(PY)/pip install -q -r backend/requirements-dev.txt
	cd blockchain && npm install --no-audit --no-fund
	cd frontend && npm install --no-audit --no-fund

demo: ## Start everything: local chain, contract, API, dashboard
	scripts/dev.sh

demo-lite: ## Start API and dashboard with a simulated ledger (no Node chain)
	scripts/dev.sh --lite

chain: ## Run a local Hardhat node on :8545
	cd blockchain && npx hardhat node --hostname 127.0.0.1

deploy: ## Deploy the contract to the local node and register the agent
	cd blockchain && npx hardhat run scripts/deploy.js --network localhost

backend: ## Run the API only (LEDGER_MODE from the environment, default memory)
	cd backend && .venv/bin/uvicorn app.main:app_factory --factory --reload --port 8000

frontend: ## Run the dashboard only
	cd frontend && npm run dev

test: test-backend test-contracts ## Run backend and contract tests

test-backend: ## Backend tests (chain tests skip when no node is running)
	cd backend && .venv/bin/python -m pytest -q

test-contracts: ## Solidity contract tests
	cd blockchain && npx hardhat test

test-chain: ## Backend-to-contract tests; needs `make chain` and `make deploy`
	cd backend && .venv/bin/python -m pytest -q -m chain -rs

lint: ## Lint the backend and type-check the dashboard
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run typecheck

build: ## Production build of the dashboard
	cd frontend && npm run build

docker-up: ## Start everything with Docker Compose
	docker compose up --build

docker-down: ## Stop the Docker Compose stack
	docker compose down -v

clean: ## Remove local state and build output
	rm -rf backend/trustchain.db .run frontend/dist blockchain/artifacts blockchain/cache blockchain/deployments
