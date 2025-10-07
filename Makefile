# Distiller WiFi Service - Development Makefile

.PHONY: help setup run lint fix build clean install uninstall

INSTALL_DIR = /opt/distiller-services
VAR_DIR = /var/lib/distiller
LOG_DIR = /var/log/distiller
SYSTEMD_DIR = /lib/systemd/system

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
	@echo "  install    Install to system (requires sudo)"
	@echo "  uninstall  Remove from system (requires sudo)"
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
	@echo "  sudo make install       # Install to system"

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

install:
	@echo "Installing Distiller WiFi Service..."
ifeq ($(DESTDIR),)
	@# Manual installation (no DESTDIR) - requires root and full setup
	@if [ $$(id -u) -ne 0 ]; then \
		echo "Error: Installation requires root privileges. Use 'sudo make install'"; \
		exit 1; \
	fi
	@command -v uv >/dev/null 2>&1 || { \
		echo "Error: uv not found. Install with:"; \
		echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"; \
		exit 1; \
	}
	@echo "Creating system directories..."
	@install -d -o root -g root -m 755 $(VAR_DIR)
	@install -d -o root -g root -m 755 $(LOG_DIR)
	@install -d -o root -g root -m 755 $(INSTALL_DIR)
	@echo "Copying application files..."
	@cp -f distiller_wifi.py $(INSTALL_DIR)/
	@cp -rf core $(INSTALL_DIR)/
	@cp -rf services $(INSTALL_DIR)/
	@cp -rf templates $(INSTALL_DIR)/
	@cp -rf static $(INSTALL_DIR)/
	@[ -d scripts ] && cp -rf scripts $(INSTALL_DIR)/ || true
	@[ -d fonts ] && cp -rf fonts $(INSTALL_DIR)/ || true
	@cp -f pyproject.toml $(INSTALL_DIR)/
	@echo "Setting up virtual environment..."
	@cd $(INSTALL_DIR) && uv venv --system-site-packages 2>/dev/null || uv venv
	@cd $(INSTALL_DIR) && uv sync
	@if [ -d /opt/distiller-sdk ]; then \
		echo "Installing Distiller SDK..."; \
		cd $(INSTALL_DIR) && uv pip install -e /opt/distiller-sdk 2>/dev/null || true; \
	fi
	@echo "Setting permissions..."
	@chmod +x $(INSTALL_DIR)/distiller_wifi.py
	@find $(INSTALL_DIR) -type d -exec chmod 755 {} \;
	@find $(INSTALL_DIR) -type f -name "*.py" -exec chmod 755 {} \;
	@[ -d $(INSTALL_DIR)/scripts ] && find $(INSTALL_DIR)/scripts -name "*.sh" -exec chmod +x {} \; || true
	@echo "Installing systemd service..."
	@cp -f distiller-wifi.service $(SYSTEMD_DIR)/distiller-wifi.service
	@systemctl daemon-reload
	@systemctl enable distiller-wifi.service 2>/dev/null || true
	@echo ""
	@echo "Installation complete!"
	@echo ""
	@echo "To start the service:"
	@echo "  systemctl start distiller-wifi"
	@echo ""
	@echo "To check service status:"
	@echo "  systemctl status distiller-wifi"
	@echo ""
	@echo "To view logs:"
	@echo "  journalctl -u distiller-wifi -f"
else
	@# Package building (DESTDIR set) - just stage files, no system operations
	@echo "Staging files to $(DESTDIR)$(INSTALL_DIR)..."
	@mkdir -p $(DESTDIR)$(VAR_DIR)
	@mkdir -p $(DESTDIR)$(LOG_DIR)
	@mkdir -p $(DESTDIR)$(INSTALL_DIR)
	@mkdir -p $(DESTDIR)$(SYSTEMD_DIR)
	@cp -f distiller_wifi.py $(DESTDIR)$(INSTALL_DIR)/
	@cp -rf core $(DESTDIR)$(INSTALL_DIR)/
	@cp -rf services $(DESTDIR)$(INSTALL_DIR)/
	@cp -rf templates $(DESTDIR)$(INSTALL_DIR)/
	@cp -rf static $(DESTDIR)$(INSTALL_DIR)/
	@[ -d scripts ] && cp -rf scripts $(DESTDIR)$(INSTALL_DIR)/ || true
	@[ -d fonts ] && cp -rf fonts $(DESTDIR)$(INSTALL_DIR)/ || true
	@cp -f pyproject.toml $(DESTDIR)$(INSTALL_DIR)/
	@cp -f distiller-wifi.service $(DESTDIR)$(SYSTEMD_DIR)/distiller-wifi.service
	@echo "Files staged successfully"
endif

uninstall:
	@echo "Uninstalling Distiller WiFi Service..."
	@if [ $$(id -u) -ne 0 ]; then \
		echo "Error: Uninstallation requires root privileges. Use 'sudo make uninstall'"; \
		exit 1; \
	fi
	@if systemctl is-active --quiet distiller-wifi; then \
		echo "Stopping distiller-wifi service..."; \
		systemctl stop distiller-wifi; \
	fi
	@if systemctl is-enabled --quiet distiller-wifi 2>/dev/null; then \
		echo "Disabling distiller-wifi service..."; \
		systemctl disable distiller-wifi; \
	fi
	@if [ -f $(SYSTEMD_DIR)/distiller-wifi.service ]; then \
		echo "Removing systemd service..."; \
		rm -f $(SYSTEMD_DIR)/distiller-wifi.service; \
		systemctl daemon-reload; \
	fi
	@if [ -d $(INSTALL_DIR) ]; then \
		echo "Removing application files..."; \
		rm -rf $(INSTALL_DIR); \
	fi
	@if command -v nmcli >/dev/null 2>&1; then \
		echo "Removing Distiller NetworkManager connections..."; \
		nmcli connection show 2>/dev/null | grep -E "^Distiller-" | awk '{print $$1}' | \
			xargs -r nmcli connection delete 2>/dev/null || true; \
	fi
	@echo ""
	@echo "Uninstallation complete!"
	@echo ""
	@echo "Note: State directory $(VAR_DIR) and logs $(LOG_DIR) were preserved."
	@echo "To remove them: sudo rm -rf $(VAR_DIR) $(LOG_DIR)"
