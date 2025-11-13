#!/bin/bash
set -e

echo "Running ruff..."
uv run ruff check

echo "Running mypy..."
uv run mypy packages/

echo "Running tests..."
uv run pytest packages/*/tests -v

echo "All checks passed!"
