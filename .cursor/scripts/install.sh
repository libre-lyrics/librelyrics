#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

python3 -m pip install --user --upgrade pip
python3 -m pip install --user -e ".[dev]"
python3 -m pip install --user librelyrics-spotify build twine
