#!/bin/bash
set -e

echo "Running mypy..."
uv run mypy packages/pylutron-integration/src packages/pylutron-integration-cli/src

echo "Running tests..."
uv run pytest packages/*/tests -v

echo "All checks passed!"
