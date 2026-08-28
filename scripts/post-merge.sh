#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python_version="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
site_packages=".pythonlibs/lib/python${python_version}/site-packages"
mkdir -p "$site_packages"

pip install \
  --disable-pip-version-check \
  --no-input \
  --prefer-binary \
  --target "$site_packages" \
  -r requirements.txt

python -m compileall -q \
  app.py \
  app_core.py \
  fetchers.py \
  nfl_features.py \
  nfl_model.py \
  scripts