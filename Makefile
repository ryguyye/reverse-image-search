PY ?= python3
VENV := .venv
BIN := $(VENV)/bin
PORT ?= 8000
APP_DIR := src
APP := selfwatch.main:app

.PHONY: help install dev run tunnel test lint clean

help:
	@echo "Targets:"
	@echo "  make install   Create .venv and install deps"
	@echo "  make dev       Run uvicorn with --reload on PORT=$(PORT)"
	@echo "  make run       Run uvicorn for production (no reload, proxy headers)"
	@echo "  make tunnel    Start a Cloudflare quick tunnel to localhost:$(PORT)"
	@echo "  make test      Lint + tests"
	@echo "  make lint      ruff check"
	@echo "  make clean     Remove .venv, caches, uploads, db"

$(VENV):
	$(PY) -m venv $(VENV)

install: $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt -r requirements-dev.txt

dev:
	PYTHONPATH=$(APP_DIR) $(BIN)/uvicorn $(APP) --reload --port $(PORT)

run:
	PYTHONPATH=$(APP_DIR) $(BIN)/uvicorn $(APP) --host 0.0.0.0 --port $(PORT) \
	  --proxy-headers --forwarded-allow-ips="*"

tunnel:
	@command -v cloudflared >/dev/null 2>&1 || { \
	  echo "cloudflared not found. Install: brew install cloudflared (macOS) or"; \
	  echo "  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"; \
	  echo "Then re-run 'make tunnel'. See docs/deploy.md for named-tunnel setup."; \
	  exit 1; \
	}
	cloudflared tunnel --url http://localhost:$(PORT)

test: lint
	PYTHONPATH=$(APP_DIR) $(BIN)/pytest -q

lint:
	$(BIN)/ruff check src tests

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache uploads selfwatch.db selfwatch.db-journal
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
