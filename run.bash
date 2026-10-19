#!/usr/bin/env bash
# Run the microsd command-line tool with any arguments.
set -euo pipefail
exec uv run microsd "$@"
