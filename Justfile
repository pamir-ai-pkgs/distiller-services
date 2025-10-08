default:
    @just --list

setup:
    uv sync

clean:
    rm -rf debian/.debhelper debian/files debian/*.log debian/*.substvars debian/distiller-services debian/debhelper-build-stamp dist
    rm -f ../*.deb ../*.dsc ../*.tar.* ../*.changes ../*.buildinfo ../*.build
    rm -rf build *.egg-info .venv uv.lock tmp *.log
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true

build arch="arm64":
    #!/usr/bin/env bash
    set -e
    export DEB_BUILD_OPTIONS="parallel=$(nproc)"
    debuild -us -uc -b -a{{arch}}
    mkdir -p dist && mv ../*.deb dist/ 2>/dev/null || true
    rm -f ../*.{dsc,tar.*,changes,buildinfo,build}

changelog:
    dch -i

run *ARGS:
    sudo -E uv run python distiller_wifi.py --no-hardware --debug {{ARGS}}

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy --ignore-missing-imports --no-strict-optional --exclude debian .

fix:
    uv run ruff check --fix .
    uv run ruff format .

status:
    @sudo systemctl status distiller-wifi 2>/dev/null || echo "Service not running"

logs follow="":
    #!/usr/bin/env bash
    if [ -n "{{follow}}" ]; then
        sudo journalctl -u distiller-wifi -f
    else
        sudo journalctl -u distiller-wifi -n 100
    fi
