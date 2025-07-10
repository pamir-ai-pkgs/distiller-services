# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Distiller CM5 Services - Claude Development Guide

## Project Overview
Comprehensive WiFi setup and network management service for Raspberry Pi CM5-based Distiller devices. Provides automated WiFi configuration with web interface, e-ink display integration, mDNS discovery, and SSH tunnel access for remote management.

**Package Management:** Uses `uv` package manager for fast, reliable dependency resolution and virtual environment management. Dependencies are defined in `pyproject.toml` with fallback support for traditional `pip` + `requirements.txt`.

## Development Guidelines

### Dependency Management
- **IMPORTANT:** Never fallback to pip, and always use UV for python dependencies and virtual environment

(Rest of the file remains unchanged...)