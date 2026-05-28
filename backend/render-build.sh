#!/usr/bin/env bash
# Exit on error
set -e

echo "Setting up Cargo for writable directory..."
export CARGO_HOME=/tmp/cargo
export CARGO_TARGET_DIR=/tmp/cargo-target

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt --break-system-packages

echo "Build completed successfully!"