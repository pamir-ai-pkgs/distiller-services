#!/bin/bash

# Development helper script for Distiller WiFi Service
# Prefers uv for fast dependency management, falls back to pip

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running in project directory
if [ ! -f "distiller_wifi.py" ]; then
    log_error "Please run this script from the project root directory"
    exit 1
fi

# Command to run
CMD="${1:-run}"
shift || true

case "$CMD" in
    setup|install)
        log_info "Setting up development environment..."
        
        # Check for uv
        if command -v uv >/dev/null 2>&1; then
            log_info "Using uv (fast mode)..."
            
            # Create virtual environment if not exists
            if [ ! -d ".venv" ]; then
                log_info "Creating virtual environment..."
                uv venv
            fi
            
            # Install dependencies
            log_info "Installing dependencies..."
            if [ -f "pyproject.toml" ]; then
                uv sync
            else
                uv pip install -r requirements.txt
            fi
            
            log_info "Setup complete! Use './dev.sh run' to start the service"
            
        else
            log_warn "uv not found, falling back to pip..."
            log_info "For faster setup, install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
            
            # Create virtual environment if not exists
            if [ ! -d ".venv" ]; then
                log_info "Creating virtual environment..."
                python3 -m venv .venv
            fi
            
            # Activate and install
            source .venv/bin/activate
            pip install --upgrade pip
            pip install -r requirements.txt
            
            log_info "Setup complete! Use './dev.sh run' to start the service"
        fi
        ;;
        
    run|start)
        log_info "Starting Distiller WiFi service in development mode..."
        
        # Default to no-hardware and debug in development
        ARGS="--no-hardware --debug $@"
        
        if command -v uv >/dev/null 2>&1; then
            log_info "Running with uv (requires sudo)..."
            sudo uv run python distiller_wifi.py $ARGS
        elif [ -f ".venv/bin/python" ]; then
            log_info "Running with virtual environment (requires sudo)..."
            sudo .venv/bin/python distiller_wifi.py $ARGS
        else
            log_error "No virtual environment found. Run './dev.sh setup' first"
            exit 1
        fi
        ;;
        
    test)
        log_info "Running tests..."
        
        if command -v uv >/dev/null 2>&1; then
            uv run pytest tests/ $@
        elif [ -f ".venv/bin/pytest" ]; then
            .venv/bin/pytest tests/ $@
        else
            log_error "pytest not installed. Run './dev.sh setup' first"
            exit 1
        fi
        ;;
        
    lint)
        log_info "Running linters..."
        
        if command -v uv >/dev/null 2>&1; then
            uv run ruff check . $@
            uv run mypy . $@
        elif [ -f ".venv/bin/ruff" ]; then
            .venv/bin/ruff check . $@
            .venv/bin/mypy . $@
        else
            log_warn "Linters not installed"
        fi
        ;;
        
    format)
        log_info "Formatting code..."
        
        if command -v uv >/dev/null 2>&1; then
            uv run black . $@
            uv run isort . $@
        elif [ -f ".venv/bin/black" ]; then
            .venv/bin/black . $@
            .venv/bin/isort . $@
        else
            log_warn "Formatters not installed"
        fi
        ;;
        
    clean)
        log_info "Cleaning up..."
        
        # Remove Python cache files
        find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        find . -name "*.pyc" -delete 2>/dev/null || true
        find . -name "*.pyo" -delete 2>/dev/null || true
        find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
        
        # Remove temporary files
        rm -rf tmp/ 2>/dev/null || true
        rm -f *.log 2>/dev/null || true
        
        log_info "Cleanup complete"
        ;;
        
    reset)
        log_info "Resetting development environment..."
        
        # Clean first
        $0 clean
        
        # Remove virtual environment
        rm -rf .venv/
        
        # Remove uv files
        rm -f uv.lock
        
        log_info "Environment reset. Run './dev.sh setup' to reinstall"
        ;;
        
    shell)
        log_info "Starting development shell..."
        
        if [ -f ".venv/bin/activate" ]; then
            log_info "Activating virtual environment..."
            exec bash --init-file <(echo "source .venv/bin/activate; echo 'Development environment activated'")
        else
            log_error "No virtual environment found. Run './dev.sh setup' first"
            exit 1
        fi
        ;;
        
    status)
        log_info "Development environment status:"
        
        # Check uv
        if command -v uv >/dev/null 2>&1; then
            echo "  uv: $(uv --version)"
        else
            echo "  uv: not installed"
        fi
        
        # Check virtual environment
        if [ -d ".venv" ]; then
            echo "  Virtual environment: .venv"
            if [ -f ".venv/bin/python" ]; then
                echo "  Python: $(.venv/bin/python --version)"
            fi
        else
            echo "  Virtual environment: not created"
        fi
        
        # Check main dependencies
        if [ -f ".venv/bin/python" ]; then
            .venv/bin/python -c "import fastapi; print(f'  FastAPI: {fastapi.__version__}')" 2>/dev/null || echo "  FastAPI: not installed"
            .venv/bin/python -c "import uvicorn; print(f'  Uvicorn: {uvicorn.__version__}')" 2>/dev/null || echo "  Uvicorn: not installed"
            .venv/bin/python -c "import pydantic; print(f'  Pydantic: {pydantic.__version__}')" 2>/dev/null || echo "  Pydantic: not installed"
        fi
        ;;
        
    help|--help|-h)
        echo "Distiller WiFi Service Development Script"
        echo ""
        echo "Usage: ./dev.sh [command] [options]"
        echo ""
        echo "Commands:"
        echo "  setup, install   Set up development environment"
        echo "  run, start       Start the service in development mode (requires sudo)"
        echo "  test            Run tests"
        echo "  lint            Run linters"
        echo "  format          Format code"
        echo "  clean           Clean temporary files"
        echo "  reset           Reset environment completely"
        echo "  shell           Start development shell"
        echo "  status          Show environment status"
        echo "  help            Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./dev.sh setup              # Initial setup"
        echo "  ./dev.sh run                # Run in dev mode with sudo (no-hardware, debug)"
        echo "  ./dev.sh run --port 9090    # Run on different port with sudo"
        echo "  ./dev.sh test               # Run all tests"
        echo "  ./dev.sh clean              # Clean up temporary files"
        ;;
        
    *)
        log_error "Unknown command: $CMD"
        echo "Run './dev.sh help' for usage information"
        exit 1
        ;;
esac