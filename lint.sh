#!/bin/bash

# lint.sh - Comprehensive linting and formatting script for Distiller CM5 Services
# Checks Python, HTML, JavaScript, CSS, JSON, YAML, Markdown, and shell scripts

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_PATH="${PROJECT_ROOT}/.venv"
EXIT_CODE=0
FIX_MODE=false
CHECK_MODE=true
VERBOSE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX_MODE=true
            CHECK_MODE=false
            shift
            ;;
        --check)
            CHECK_MODE=true
            FIX_MODE=false
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
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
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Utility functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

run_command() {
    local cmd="$1"
    local description="$2"
    
    if [ "$VERBOSE" = true ]; then
        echo -e "${BLUE}Running:${NC} $cmd"
    fi
    
    if eval "$cmd" 2>&1 | ([ "$VERBOSE" = true ] && cat || cat > /dev/null); then
        log_success "$description"
        return 0
    else
        log_error "$description"
        return 1
    fi
}

# Check if running with uv or standard venv
if command -v uv &> /dev/null; then
    RUNNER="uv run"
    log_info "Using uv for package management"
else
    RUNNER=""
    if [ -f "$VENV_PATH/bin/activate" ]; then
        source "$VENV_PATH/bin/activate"
        log_info "Using virtual environment at $VENV_PATH"
    else
        log_warning "No virtual environment found, using system Python"
    fi
fi

# Header
echo "======================================"
echo "   Distiller CM5 Services Linter"
if [ "$FIX_MODE" = true ]; then
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
if command -v ruff &> /dev/null || command -v "$VENV_PATH/bin/ruff" &> /dev/null; then
    if [ "$FIX_MODE" = true ]; then
        if ! run_command "$RUNNER ruff check --fix ." "Ruff auto-fix"; then
            EXIT_CODE=1
        fi
        if ! run_command "$RUNNER ruff format ." "Ruff format"; then
            EXIT_CODE=1
        fi
    else
        if ! run_command "$RUNNER ruff check ." "Ruff check"; then
            EXIT_CODE=1
        fi
        if ! run_command "$RUNNER ruff format --check ." "Ruff format check"; then
            EXIT_CODE=1
        fi
    fi
else
    # Fallback to traditional tools
    
    # Black - Python formatter
    if command -v black &> /dev/null || command -v "$VENV_PATH/bin/black" &> /dev/null; then
        if [ "$FIX_MODE" = true ]; then
            if ! run_command "$RUNNER black ." "Black format"; then
                EXIT_CODE=1
            fi
        else
            if ! run_command "$RUNNER black --check ." "Black check"; then
                EXIT_CODE=1
            fi
        fi
    else
        log_warning "Black not installed"
    fi
    
    # isort - Import sorter
    if command -v isort &> /dev/null || command -v "$VENV_PATH/bin/isort" &> /dev/null; then
        if [ "$FIX_MODE" = true ]; then
            if ! run_command "$RUNNER isort ." "isort format"; then
                EXIT_CODE=1
            fi
        else
            if ! run_command "$RUNNER isort --check-only ." "isort check"; then
                EXIT_CODE=1
            fi
        fi
    else
        log_warning "isort not installed"
    fi
    
    # Flake8 - Python linter
    if command -v flake8 &> /dev/null || command -v "$VENV_PATH/bin/flake8" &> /dev/null; then
        if ! run_command "$RUNNER flake8 --extend-ignore=E203,W503 --max-line-length=100 ." "Flake8 check"; then
            EXIT_CODE=1
        fi
    else
        log_warning "Flake8 not installed"
    fi
fi

# MyPy - Type checker
if command -v mypy &> /dev/null || command -v "$VENV_PATH/bin/mypy" &> /dev/null; then
    if ! run_command "$RUNNER mypy --ignore-missing-imports --no-strict-optional ." "MyPy type check"; then
        EXIT_CODE=1
    fi
else
    log_warning "MyPy not installed"
fi

echo ""

# HTML Linting
echo "HTML Files"
echo "----------"

# djlint - Django/Jinja2 template linter
if command -v djlint &> /dev/null || command -v "$VENV_PATH/bin/djlint" &> /dev/null; then
    if [ "$FIX_MODE" = true ]; then
        if ! run_command "$RUNNER djlint templates/ --reformat" "djlint format"; then
            EXIT_CODE=1
        fi
    else
        if ! run_command "$RUNNER djlint templates/ --check" "djlint check"; then
            EXIT_CODE=1
        fi
    fi
else
    log_warning "djlint not installed (pip install djlint)"
fi

echo ""

# JavaScript Linting
echo "JavaScript Files"
echo "----------------"

# ESLint - JavaScript linter
if command -v eslint &> /dev/null || [ -f "node_modules/.bin/eslint" ]; then
    ESLINT_CMD="eslint"
    [ -f "node_modules/.bin/eslint" ] && ESLINT_CMD="node_modules/.bin/eslint"
    
    if [ "$FIX_MODE" = true ]; then
        if ! run_command "$ESLINT_CMD --fix static/js/" "ESLint auto-fix"; then
            EXIT_CODE=1
        fi
    else
        if ! run_command "$ESLINT_CMD static/js/" "ESLint check"; then
            EXIT_CODE=1
        fi
    fi
else
    log_warning "ESLint not installed (npm install -g eslint)"
fi

echo ""

# CSS Linting
echo "CSS Files"
echo "---------"

# Stylelint - CSS linter
if command -v stylelint &> /dev/null || [ -f "node_modules/.bin/stylelint" ]; then
    STYLELINT_CMD="stylelint"
    [ -f "node_modules/.bin/stylelint" ] && STYLELINT_CMD="node_modules/.bin/stylelint"
    
    if [ "$FIX_MODE" = true ]; then
        if ! run_command "$STYLELINT_CMD --fix 'static/css/*.css'" "Stylelint auto-fix"; then
            EXIT_CODE=1
        fi
    else
        if ! run_command "$STYLELINT_CMD 'static/css/*.css'" "Stylelint check"; then
            EXIT_CODE=1
        fi
    fi
else
    log_warning "Stylelint not installed (npm install -g stylelint stylelint-config-standard)"
fi

echo ""

# JSON/YAML Linting
echo "JSON/YAML Files"
echo "---------------"

# JSON validation
for file in $(find . -name "*.json" -not -path "./.venv/*" -not -path "./node_modules/*" -not -path "./.git/*" -not -path "./.mypy_cache/*" -not -path "./.pytest_cache/*" -not -path "./htmlcov/*" -not -path "./build/*" -not -path "./dist/*" 2>/dev/null); do
    if python -m json.tool "$file" > /dev/null 2>&1; then
        [ "$VERBOSE" = true ] && log_success "Valid JSON: $file"
    else
        log_error "Invalid JSON: $file"
        EXIT_CODE=1
    fi
done

# YAML linting
if command -v yamllint &> /dev/null; then
    if ! run_command "yamllint -d relaxed ." "YAML lint"; then
        EXIT_CODE=1
    fi
else
    log_warning "yamllint not installed (pip install yamllint)"
fi

echo ""

# Markdown Linting
echo "Markdown Files"
echo "--------------"

if command -v markdownlint &> /dev/null || command -v markdownlint-cli &> /dev/null; then
    MD_CMD="markdownlint"
    command -v markdownlint-cli &> /dev/null && MD_CMD="markdownlint-cli"
    
    if [ "$FIX_MODE" = true ]; then
        if ! run_command "$MD_CMD --fix '**/*.md'" "Markdown auto-fix"; then
            EXIT_CODE=1
        fi
    else
        if ! run_command "$MD_CMD '**/*.md'" "Markdown check"; then
            EXIT_CODE=1
        fi
    fi
else
    log_warning "markdownlint not installed (npm install -g markdownlint-cli)"
fi

echo ""

# Shell Script Linting
echo "Shell Scripts"
echo "-------------"

if command -v shellcheck &> /dev/null; then
    for file in $(find . -name "*.sh" -not -path "./.venv/*" -not -path "./node_modules/*" -not -path "./.git/*" -not -path "./.mypy_cache/*" -not -path "./build/*" -not -path "./dist/*" 2>/dev/null); do
        if run_command "shellcheck '$file'" "shellcheck: $(basename $file)"; then
            [ "$VERBOSE" = true ] && log_success "Valid shell script: $file"
        else
            EXIT_CODE=1
        fi
    done
else
    log_warning "shellcheck not installed (apt install shellcheck)"
fi

echo ""

# Prettier - Universal formatter (if available)
if command -v prettier &> /dev/null || [ -f "node_modules/.bin/prettier" ]; then
    PRETTIER_CMD="prettier"
    [ -f "node_modules/.bin/prettier" ] && PRETTIER_CMD="node_modules/.bin/prettier"
    
    echo "Prettier (Universal Formatter)"
    echo "------------------------------"
    
    if [ "$FIX_MODE" = true ]; then
        if ! run_command "$PRETTIER_CMD --write '**/*.{js,css,html,json,yaml,yml,md}' --ignore-path .gitignore" "Prettier format"; then
            EXIT_CODE=1
        fi
    else
        if ! run_command "$PRETTIER_CMD --check '**/*.{js,css,html,json,yaml,yml,md}' --ignore-path .gitignore" "Prettier check"; then
            EXIT_CODE=1
        fi
    fi
    echo ""
fi

# Summary
echo "======================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}All checks passed!${NC}"
else
    echo -e "${RED}Some checks failed!${NC}"
    if [ "$CHECK_MODE" = true ]; then
        echo ""
        echo "Run with --fix to auto-fix formatting issues"
    fi
fi
echo "======================================"

exit $EXIT_CODE