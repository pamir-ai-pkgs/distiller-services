#!/bin/bash

# Build script for Distiller CM5 Services Debian package
# Uses modern debian packaging tools and best practices
# Specifically targets arm64 and all architectures for Raspberry Pi CM5

set -e

# Configuration
PACKAGE_NAME="distiller-cm5-services"
BUILD_DIR="build"
DIST_DIR="dist"
TARGET_ARCHITECTURES="arm64 all"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to get current architecture
get_current_arch() {
    dpkg --print-architecture 2>/dev/null || uname -m
}

# Function to install build dependencies
install_build_deps() {
    print_status "Checking build dependencies..."
    
    local missing_deps=()
    
    # Check for required commands
    if ! command_exists dpkg-buildpackage; then
        missing_deps+=("dpkg-dev")
    fi
    
    if ! command_exists dh; then
        missing_deps+=("debhelper")
    fi
    
    if ! command_exists dh_python3; then
        missing_deps+=("dh-python")
    fi
    
    # Check for python3-dev and python3-setuptools
    if ! dpkg -l python3-dev >/dev/null 2>&1; then
        missing_deps+=("python3-dev")
    fi
    
    if ! dpkg -l python3-setuptools >/dev/null 2>&1; then
        missing_deps+=("python3-setuptools")
    fi
    
    # Check for cross-compilation tools if building for arm64
    local current_arch=$(get_current_arch)
    if [[ "$current_arch" != "arm64" ]] && [[ " $TARGET_ARCHITECTURES " =~ " arm64 " ]]; then
        if ! command_exists dpkg-cross; then
            missing_deps+=("dpkg-cross")
        fi
        
        if ! command_exists crossbuild-essential-arm64; then
            missing_deps+=("crossbuild-essential-arm64")
        fi
    fi
    
    # Check for lintian (optional but recommended)
    if ! command_exists lintian; then
        missing_deps+=("lintian")
    fi
    
    # Check for devscripts (optional but recommended)
    if ! command_exists debuild; then
        missing_deps+=("devscripts")
    fi
    
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_warning "Missing build dependencies: ${missing_deps[*]}"
        print_status "Installing build dependencies..."
        
        if command_exists apt-get; then
            sudo apt-get update
            sudo apt-get install -y "${missing_deps[@]}"
        elif command_exists apt; then
            sudo apt update
            sudo apt install -y "${missing_deps[@]}"
        else
            print_error "Could not install dependencies. Please install manually: ${missing_deps[*]}"
            exit 1
        fi
    fi
    
    print_success "All build dependencies are available"
}

# Function to clean build artifacts
clean_build() {
    print_status "Cleaning build artifacts..."
    
    # Remove build directories
    sudo rm -rf "$BUILD_DIR"
    sudo rm -rf debian/tmp
    sudo rm -rf debian/.debhelper
    sudo rm -rf debian/files
    sudo rm -rf debian/debhelper-build-stamp
    sudo rm -rf debian/${PACKAGE_NAME}
    
    # Remove generated files
    sudo rm -f debian/${PACKAGE_NAME}.*.debhelper
    sudo rm -f debian/${PACKAGE_NAME}.*.log
    sudo rm -f debian/${PACKAGE_NAME}.debhelper.log
    sudo rm -f debian/${PACKAGE_NAME}.postinst.debhelper
    sudo rm -f debian/${PACKAGE_NAME}.postrm.debhelper
    sudo rm -f debian/${PACKAGE_NAME}.prerm.debhelper
    sudo rm -f debian/${PACKAGE_NAME}.substvars
    
    # Remove any .pyc files
    sudo find . -name "*.pyc" -delete
    sudo find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Remove any existing build artifacts
    sudo rm -f ../${PACKAGE_NAME}_*.deb
    sudo rm -f ../${PACKAGE_NAME}_*.dsc
    sudo rm -f ../${PACKAGE_NAME}_*.changes
    sudo rm -f ../${PACKAGE_NAME}_*.buildinfo
    sudo rm -f ../${PACKAGE_NAME}_*.tar.*

    # Remove dist directory if it exists
    if [ -d "$DIST_DIR" ]; then
		sudo rm -rf "$DIST_DIR"
	fi
    
    print_success "Build artifacts cleaned"
}

# Function to validate package structure
validate_package() {
    print_status "Validating package structure..."
    
    # Check for required files
    local required_files=(
        "debian/control"
        "debian/changelog"
        "debian/rules"
        "debian/copyright"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required file missing: $file"
            exit 1
        fi
    done
    
    # Check if rules file is executable
    if [ ! -x "debian/rules" ]; then
        print_status "Making debian/rules executable..."
        chmod +x debian/rules
    fi
    
    # Check for Python files
    if [ ! -f "distiller_wifi.py" ]; then
        print_error "Main Python file missing: distiller_wifi.py"
        exit 1
    fi
    
    print_success "Package structure validated"
}

# Function to build source package
build_source() {
    print_status "Building source package..."
    
    # Create source package
    CC="aarch64-linux-gnu-gcc" dpkg-buildpackage -S -us -uc -d -aarm64
    
    print_success "Source package built"
}

# Function to build binary package for specific architecture
build_binary_for_arch() {
    # Try with dpkg-buildpackage first
    CC="aarch64-linux-gnu-gcc" dpkg-buildpackage -b -us -uc -d -aarm64
}

# Function to build binary package for all target architectures
build_binary() {
    print_status "Building binary packages for target architectures: $TARGET_ARCHITECTURES"
    
    local current_arch=$(get_current_arch)
    print_status "Current architecture: $current_arch"
    
    for arch in $TARGET_ARCHITECTURES; do
        if [[ "$arch" == "all" ]]; then
            print_status "Building 'all' architecture package..."
            build_binary_for_arch "all"
        elif [[ "$arch" == "arm64" ]]; then
            print_status "Building arm64 architecture package..."
            build_binary_for_arch "arm64"
        else
            print_warning "Skipping unsupported architecture: $arch"
        fi
    done
}

# Function to build both source and binary packages
build_full() {
    print_status "Building full package (source + binary) for target architectures: $TARGET_ARCHITECTURES"
    
    # Build source package first
    build_source
    
    # Build binary packages for each target architecture
    build_binary
}

# Function to run lintian checks
run_lintian() {
    print_status "Running lintian checks..."
    
    if command_exists lintian; then
        # Find all .deb files for target architectures
        local deb_files=()
        for arch in $TARGET_ARCHITECTURES; do
            if [[ "$arch" == "all" ]]; then
                local all_deb=$(find .. -name "${PACKAGE_NAME}_*_all.deb" -type f | head -1)
                if [ -n "$all_deb" ]; then
                    deb_files+=("$all_deb")
                fi
            elif [[ "$arch" == "arm64" ]]; then
                local arm64_deb=$(find .. -name "${PACKAGE_NAME}_*_arm64.deb" -type f | head -1)
                if [ -n "$arm64_deb" ]; then
                    deb_files+=("$arm64_deb")
                fi
            fi
        done
        
        if [ ${#deb_files[@]} -gt 0 ]; then
            for deb_file in "${deb_files[@]}"; do
                print_status "Checking package: $deb_file"
                lintian "$deb_file" || print_warning "Lintian found some issues (non-fatal)"
            done
        else
            print_warning "No .deb files found for target architectures"
        fi
    else
        print_warning "Lintian not available, skipping checks"
    fi
}

# Function to organize build artifacts
organize_artifacts() {
    print_status "Organizing build artifacts..."
    
    # Create dist directory
    mkdir -p "$DIST_DIR"
    
    # Move build artifacts to dist directory, filtering for target architectures
    for extension in deb dsc changes buildinfo; do
        for file in ../${PACKAGE_NAME}_*.${extension}; do
            if [ -f "$file" ]; then
                local filename=$(basename "$file")
                local should_move=false
                
                # Always move source files (dsc, source buildinfo, tar.*)
                if [[ "$extension" == "dsc" ]] || [[ "$filename" == *"_source.buildinfo" ]] || [[ "$filename" == *".tar."* ]]; then
                    should_move=true
                else
                    # For other files, only move if they match target architectures
                    for arch in $TARGET_ARCHITECTURES; do
                        if [[ "$filename" == *"_${arch}.${extension}" ]]; then
                            should_move=true
                            break
                        fi
                    done
                fi
                
                if [[ "$should_move" == "true" ]]; then
                    mv -f "$file" "$DIST_DIR/" 2>/dev/null || true
                else
                    print_status "Skipping non-target architecture file: $filename"
                    rm -f "$file" 2>/dev/null || true
                fi
            fi
        done
    done
    
    # Handle tar files (which can have various extensions like .tar.gz, .tar.xz, etc.)
    for file in ../${PACKAGE_NAME}_*.tar.*; do
        if [ -f "$file" ]; then
            mv -f "$file" "$DIST_DIR/" 2>/dev/null || true
        fi
    done
    
    # Show what was created
    if [ -d "$DIST_DIR" ] && [ "$(ls -A "$DIST_DIR" 2>/dev/null)" ]; then
        print_success "Build artifacts created in $DIST_DIR/:"
        ls -la "$DIST_DIR/"
    else
        print_warning "No build artifacts found"
    fi
}

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS] [COMMAND]"
    echo
    echo "Build Debian packages for Distiller CM5 Services"
    echo "Target architectures: $TARGET_ARCHITECTURES"
    echo
    echo "Commands:"
    echo "  clean      Clean build artifacts"
    echo "  source     Build source package only"
    echo "  binary     Build binary package only"
    echo "  full       Build both source and binary packages (default)"
    echo "  check      Run lintian checks on existing packages"
    echo "  deps       Install build dependencies"
    echo
    echo "Options:"
    echo "  -v VERSION Set package version (updates changelog)"
    echo "  -h         Show this help message"
    echo
    echo "Examples:"
    echo "  $0                    # Build full package for arm64 and all"
    echo "  $0 -v 1.0.1-1 full  # Build with specific version"
    echo "  $0 clean binary      # Clean then build binary package"
    echo "  $0 deps              # Install build dependencies"
}

# Parse command line arguments
VERSION=""
COMMAND="full"

while getopts "v:h" opt; do
    case $opt in
        v)
            VERSION="$OPTARG"
            ;;
        h)
            usage
            exit 0
            ;;
        \?)
            print_error "Invalid option: -$OPTARG"
            usage
            exit 1
            ;;
    esac
done

shift $((OPTIND-1))

# Set command if provided
if [ $# -gt 0 ]; then
    COMMAND="$1"
fi

# Main execution
print_status "Starting Debian package build for $PACKAGE_NAME"
print_status "Command: $COMMAND"
print_status "Target architectures: $TARGET_ARCHITECTURES"

case "$COMMAND" in
    clean)
        clean_build
        exit 0
        ;;
    deps)
        install_build_deps
        ;;
    source)
        install_build_deps
        validate_package
        build_source
        organize_artifacts
        ;;
    binary)
        install_build_deps
        validate_package
        build_binary
        organize_artifacts
        run_lintian
        ;;
    full)
        install_build_deps
        validate_package
        build_full
        organize_artifacts
        run_lintian
        ;;
    check)
        run_lintian
        ;;
    *)
        print_error "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac

print_success "Build process completed successfully!"

# Show final status
if [ -d "$DIST_DIR" ] && [ "$(ls -A "$DIST_DIR")" ]; then
    echo
    print_status "Generated packages:"
    ls -la "$DIST_DIR/"
    echo
    print_status "To install the package, run:"
    echo "  sudo dpkg -i $DIST_DIR/${PACKAGE_NAME}_*_all.deb"
    echo "  sudo dpkg -i $DIST_DIR/${PACKAGE_NAME}_*_arm64.deb  # For arm64 systems"
    echo "  sudo apt-get install -f  # Fix any dependency issues"
fi 
