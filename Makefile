# Engram developer Makefile
.DEFAULT_GOAL := help
.PHONY: help install up down migrate seed api dashboard capture test lint typecheck check fmt

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install package + dev + dashboard extras (editable)
	pip install -e ".[dev,dashboard]"

up:  ## Start Postgres + Qdrant
	docker compose up -d

down:  ## Stop infrastructure
	docker compose down

migrate:  ## Apply DB migrations + bootstrap tenant + ensure Qdrant collection
	alembic upgrade head
	python -m engram.cli bootstrap

seed:  ## Print the runbook to seed REAL incidents
	@echo "Follow scripts/seed_runbook.md to deploy the demo topology and capture real incidents."

api:  ## Run the FastAPI server
	python -m engram.cli serve

dashboard:  ## Run the Streamlit dashboard (talks to the API)
	python -m engram.cli dashboard

capture:  ## Run an interactive capture session (see --help)
	python -m engram.cli capture --help

test:  ## Run the test suite
	pytest -q

lint:  ## Ruff lint
	ruff check src tests

fmt:  ## Ruff autofix + format
	ruff check --fix src tests
	ruff format src tests

typecheck:  ## mypy
	mypy src

check: lint typecheck test  ## Lint + typecheck + test
