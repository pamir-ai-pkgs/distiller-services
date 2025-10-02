# Distiller WiFi Service - Development Makefile

.PHONY: help setup run lint fix build clean

# Default target
help:
	@echo "Distiller WiFi Service - Development Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  setup      Install dependencies with uv"
	@echo "  run        Start service (requires sudo, dev mode)"
	@echo "  lint       Check code (ruff, mypy, shellcheck)"
	@echo "  fix        Auto-fix formatting issues"
	@echo "  build      Build Debian package (clean + build)"
	@echo "  clean      Remove Python cache files"
	@echo "  help       Show this help message"
	@echo ""
	@echo "Examples:"
	@echo "  make setup              # Initial setup"
	@echo "  make run                # Run in dev mode"
	@echo "  make run PORT=9090      # Run on port 9090"
	@echo "  make lint               # Check all code"
	@echo "  make fix                # Auto-fix formatting"
	@echo "  make build              # Build .deb package"

setup:
	@command -v uv >/dev/null 2>&1 || { \
		echo "Error: uv not found. Install with:"; \
		echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; \
	}
	@echo "Installing dependencies..."
	uv sync 2>/dev/null

run:
	@command -v uv >/dev/null 2>&1 || { echo "Error: Run 'make setup' first"; exit 1; }
	@echo "Starting service in dev mode..."
	sudo uv run python distiller_wifi.py --no-hardware --debug $(ARGS)

lint:
	@echo "Running linters..."
	@uv run ruff check . || true
	@uv run ruff format --check . || true
	@uv run mypy --ignore-missing-imports --no-strict-optional --exclude debian . || true
	@command -v shellcheck >/dev/null 2>&1 && \
		find . -name "*.sh" -not -path "./.venv/*" -not -path "./debian/*" -exec shellcheck {} \; || \
		echo "Warning: shellcheck not installed"

fix:
	@echo "Auto-fixing code..."
	uv run ruff check --fix .
	uv run ruff format .

build:
	@echo "Building Debian package..."
	./build-deb.sh clean && ./build-deb.sh

clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@find . -name "*.pyo" -delete 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf tmp/ *.log 2>/dev/null || true
	@echo "Done"
