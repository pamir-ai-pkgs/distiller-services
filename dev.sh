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
        if ! command -v uv >/dev/null 2>&1; then
            log_error "uv not found!"
            log_info ""
            log_info "uv is required for development. Please install it first:"
            log_info "  curl -LsSf https://astral.sh/uv/install.sh | sh"
            log_info ""
            log_info "After installation, add it to your PATH:"
            log_info "  export PATH=\"\$HOME/.cargo/bin:\$PATH\""
            log_info ""
            log_info "Then run this command again."
            exit 1
        fi
        
        log_info "Using uv for dependency management..."
        
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
                    echo "  HTML:       htmlhint, djlint, prettier"
                    echo "  JavaScript: eslint, prettier"
                    echo "  CSS:        stylelint, prettier"
                    echo "  JSON/YAML:  prettier, yamllint"
                    echo "  Markdown:   markdownlint, prettier"
                    echo "  Shell:      shellcheck"
                    echo ""
                    echo "Note: Run 'npm install' to install JavaScript/CSS/HTML linting tools"
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

        # HTML/Template Linting
        echo "HTML/Template Files"
        echo "-------------------"

        # Check if Node.js is available for HTMLHint
        if command -v node >/dev/null 2>&1 && [ -f "node_modules/.bin/htmlhint" ]; then
            if [ "$LINT_FIX_MODE" = true ]; then
                # HTMLHint doesn't have auto-fix, but we can format with Prettier
                if ! run_command "npx prettier --write 'templates/**/*.html'" "Prettier HTML format" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            else
                if ! run_command "npx htmlhint templates/**/*.html" "HTMLHint check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            fi
        else
            # Fallback to djlint for Jinja2 templates
            if command -v djlint >/dev/null 2>&1 || command -v "$VENV_PATH/bin/djlint" >/dev/null 2>&1; then
                if [ "$LINT_FIX_MODE" = true ]; then
                    if ! run_command "$RUNNER djlint templates/ --reformat" "djlint format templates" "$LINT_VERBOSE"; then
                        LINT_EXIT_CODE=1
                    fi
                else
                    if ! run_command "$RUNNER djlint templates/ --check" "djlint check templates" "$LINT_VERBOSE"; then
                        LINT_EXIT_CODE=1
                    fi
                fi
            else
                log_warn "Neither HTMLHint nor djlint installed"
            fi
        fi

        echo ""

        # JavaScript Linting
        echo "JavaScript Files"
        echo "----------------"

        # Check if Node.js is available for ESLint
        if command -v node >/dev/null 2>&1 && [ -f "node_modules/.bin/eslint" ]; then
            if [ "$LINT_FIX_MODE" = true ]; then
                if ! run_command "npx eslint static/js/**/*.js --fix" "ESLint auto-fix" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "npx prettier --write 'static/js/**/*.js'" "Prettier JS format" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            else
                if ! run_command "npx eslint static/js/**/*.js" "ESLint check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "npx prettier --check 'static/js/**/*.js'" "Prettier JS check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            fi
        else
            log_warn "ESLint not installed (run 'npm install' to install frontend tools)"
        fi

        echo ""

        # CSS Linting
        echo "CSS Files"
        echo "---------"

        # Check if Node.js is available for Stylelint
        if command -v node >/dev/null 2>&1 && [ -f "node_modules/.bin/stylelint" ]; then
            if [ "$LINT_FIX_MODE" = true ]; then
                if ! run_command "npx stylelint 'static/css/**/*.css' --fix" "Stylelint auto-fix" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "npx prettier --write 'static/css/**/*.css'" "Prettier CSS format" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            else
                if ! run_command "npx stylelint 'static/css/**/*.css'" "Stylelint check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "npx prettier --check 'static/css/**/*.css'" "Prettier CSS check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            fi
        else
            log_warn "Stylelint not installed (run 'npm install' to install frontend tools)"
        fi

        echo ""

        # JSON validation (basic check)
        echo "JSON/YAML Files"
        echo "---------------"
        
        for file in $(find . -name "*.json" -not -path "./.venv/*" -not -path "./.git/*" -not -path "./node_modules/*" -not -path "./build/*" -not -path "./dist/*" -not -path "./debian/*" 2>/dev/null); do
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

        # JSON/YAML formatting with Prettier (if available)
        if command -v node >/dev/null 2>&1 && [ -f "node_modules/.bin/prettier" ]; then
            if [ "$LINT_FIX_MODE" = true ]; then
                if ! run_command "npx prettier --write '**/*.{json,yaml,yml}' --ignore-path .prettierignore" "Prettier JSON/YAML format" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            else
                if ! run_command "npx prettier --check '**/*.{json,yaml,yml}' --ignore-path .prettierignore" "Prettier JSON/YAML check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            fi
        fi

        echo ""

        # Markdown Linting
        echo "Markdown Files"
        echo "--------------"

        # Check if Node.js is available for markdownlint
        if command -v node >/dev/null 2>&1 && [ -f "node_modules/.bin/markdownlint" ]; then
            if [ "$LINT_FIX_MODE" = true ]; then
                if ! run_command "npx markdownlint '**/*.md' --fix --ignore node_modules --ignore .venv --ignore debian" "Markdownlint auto-fix" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "npx prettier --write '**/*.md' --ignore-path .prettierignore" "Prettier Markdown format" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            else
                if ! run_command "npx markdownlint '**/*.md' --ignore node_modules --ignore .venv --ignore debian" "Markdownlint check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
                if ! run_command "npx prettier --check '**/*.md' --ignore-path .prettierignore" "Prettier Markdown check" "$LINT_VERBOSE"; then
                    LINT_EXIT_CODE=1
                fi
            fi
        else
            log_warn "Markdownlint not installed (run 'npm install' to install frontend tools)"
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