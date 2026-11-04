#!/usr/bin/env bash
set -euo pipefail

cd /Users/mickey/Documents/linkfish/macos
source .venv/bin/activate
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
python wow_fishing_mac.py