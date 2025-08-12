#!/bin/bash

# Development helper script for Distiller WiFi Service
# Prefers uv for fast dependency management, falls back to pip

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

run_command() {
    local cmd="$1"
    local description="$2"
    local verbose="$3"
    
    if [ "$verbose" = true ]; then
        echo -e "${BLUE}Running:${NC} $cmd"
    fi
    
    if eval "$cmd" 2>&1 | ([ "$verbose" = true ] && cat || cat > /dev/null); then
        log_success "$description"
        return 0
    else
        log_error "$description"
        return 1
    fi
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
        # Parse lint-specific arguments
        LINT_EXIT_CODE=0
        LINT_FIX_MODE=false
        LINT_CHECK_MODE=true
        LINT_VERBOSE=false
        LINT_ARGS=()
        
        # Parse arguments for lint subcommand
        while [[ $# -gt 0 ]]; do
            case $1 in
                --fix)
                    LINT_FIX_MODE=true
                    LINT_CHECK_MODE=false
                    shift
                    ;;
                --check)
                    LINT_CHECK_MODE=true
                    LINT_FIX_MODE=false
                    shift
                    ;;
                --verbose|-v)
                    LINT_VERBOSE=true
                    shift
                    ;;
                --help|-h)
                    echo "Usage: ./dev.sh lint [OPTIONS]"
                    echo ""
                    echo "Options:"
                    echo "  --check     Check for linting issues (default)"
                    echo "  --fix       Auto-fix formatting issues"
                    echo "  --verbose   Show detailed output"
                    echo "  --help      Show this help message"
                    echo ""
                    echo "Tools used:"
                    echo "  Python:     ruff, black, isort, mypy"
                    echo "  HTML:       djlint, prettier"
                    echo "  JavaScript: eslint, prettier"
                    echo "  CSS:        stylelint, prettier"
                    echo "  JSON/YAML:  prettier, yamllint"
                    echo "  Markdown:   markdownlint"
                    echo "  Shell:      shellcheck"
                    exit 0
                    ;;
                *)
                    LINT_ARGS+=("$1")
                    shift
                    ;;
            esac
        done

        # Set up runner
        if command -v uv >/dev/null 2>&1; then
            RUNNER="uv run"
            VENV_PATH=".venv"
        elif [ -f ".venv/bin/activate" ]; then
            RUNNER=""
            source .venv/bin/activate
            VENV_PATH=".venv"
        else
            log_warn "No package manager or virtual environment found"
            RUNNER=""
            VENV_PATH=""
        fi

        echo "======================================"
        echo "   Distiller CM5 Services Linter"
        if [ "$LINT_FIX_MODE" = true ]; then
            echo "        MODE: AUTO-FIX"
        else
            echo "        MODE: CHECK"
        fi
        echo "======================================"
        echo ""

        # Python Linting
        echo "Python Files"
        echo "------------"

        # Ruff - Fast Python linter and formatter
        if command -v ruff >/dev/null 2>&1 || command -v "$VENV_PATH/bin/ruff" >/dev/null 2>&1; then
            if [ "$LINT_FIX_MODE" = true ]; then
                if ! run_command "$RUNNER ruff check --fix ." "Ruff auto-fix" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "$RUNNER ruff format ." "Ruff format" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            else
                if ! run_command "$RUNNER ruff check ." "Ruff check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "$RUNNER ruff format --check ." "Ruff format check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            fi
        else
            # Fallback to traditional tools
            
            # Black - Python formatter
            if command -v black >/dev/null 2>&1 || command -v "$VENV_PATH/bin/black" >/dev/null 2>&1; then
                if [ "$LINT_FIX_MODE" = true ]; then
                    if ! run_command "$RUNNER black ." "Black format" "$LINT_VERBOSE"; then
                        LINT_EXIT_CODE=1
                    fi
                else
                    if ! run_command "$RUNNER black --check ." "Black check" "$LINT_VERBOSE"; then
                        LINT_EXIT_CODE=1
                    fi
                fi
            else
                log_warn "Black not installed"
            fi
            
            # isort - Import sorter
            if command -v isort >/dev/null 2>&1 || command -v "$VENV_PATH/bin/isort" >/dev/null 2>&1; then
                if [ "$LINT_FIX_MODE" = true ]; then
                    if ! run_command "$RUNNER isort ." "isort format" "$LINT_VERBOSE"; then
                        LINT_EXIT_CODE=1
                    fi
                else
                    if ! run_command "$RUNNER isort --check-only ." "isort check" "$LINT_VERBOSE"; then
                        LINT_EXIT_CODE=1
                    fi
                fi
            else
                log_warn "isort not installed"
            fi
        fi

        # MyPy - Type checker
        if command -v mypy >/dev/null 2>&1 || command -v "$VENV_PATH/bin/mypy" >/dev/null 2>&1; then
            if ! run_command "$RUNNER mypy --ignore-missing-imports --no-strict-optional --exclude debian ." "MyPy type check" "$LINT_VERBOSE"; then
                LINT_EXIT_CODE=1
            fi
        else
            log_warn "MyPy not installed"
        fi

        echo ""

        # JSON validation (basic check)
        echo "JSON/YAML Files"
        echo "---------------"
        
        for file in $(find . -name "*.json" -not -path "./.venv/*" -not -path "./.git/*" -not -path "./build/*" -not -path "./dist/*" -not -path "./debian/*" 2>/dev/null); do
            if python3 -m json.tool "$file" > /dev/null 2>&1; then
                [ "$LINT_VERBOSE" = true ] && log_success "Valid JSON: $file"
            else
                log_error "Invalid JSON: $file"
                LINT_EXIT_CODE=1
            fi
        done

        # YAML linting
        if command -v yamllint >/dev/null 2>&1; then
            if ! run_command "yamllint -d relaxed ." "YAML lint" "$LINT_VERBOSE"; then
                LINT_EXIT_CODE=1
            fi
        else
            log_warn "yamllint not installed (pip install yamllint)"
        fi

        echo ""

        # Shell Script Linting
        echo "Shell Scripts"
        echo "-------------"

        if command -v shellcheck >/dev/null 2>&1; then
            for file in $(find . -name "*.sh" -not -path "./.venv/*" -not -path "./.git/*" -not -path "./build/*" -not -path "./dist/*" -not -path "./debian/*" 2>/dev/null); do
                if run_command "shellcheck '$file'" "shellcheck: $(basename $file)" "$LINT_VERBOSE"; then
                    [ "$LINT_VERBOSE" = true ] && log_success "Valid shell script: $file"
                else
                    LINT_EXIT_CODE=1
                fi
            done
        else
            log_warn "shellcheck not installed (apt install shellcheck)"
        fi

        echo ""

        # Summary
        echo "======================================"
        if [ $LINT_EXIT_CODE -eq 0 ]; then
            echo -e "${GREEN}All checks passed!${NC}"
        else
            echo -e "${RED}Some checks failed!${NC}"
            if [ "$LINT_CHECK_MODE" = true ]; then
                echo ""
                echo "Run with --fix to auto-fix formatting issues"
            fi
        fi
        echo "======================================"

        exit $LINT_EXIT_CODE
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
        echo "  lint [options]   Run comprehensive linters (--fix, --verbose, --help)"
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
        echo "  ./dev.sh lint               # Check code with all linters"
        echo "  ./dev.sh lint --fix         # Auto-fix formatting issues"
        echo "  ./dev.sh lint --verbose     # Detailed linting output"
        echo "  ./dev.sh clean              # Clean up temporary files"
        ;;
        
    *)
        log_error "Unknown command: $CMD"
        echo "Run './dev.sh help' for usage information"
        exit 1
        ;;
esac