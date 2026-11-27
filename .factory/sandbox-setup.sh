#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/node"
curl -fsSL https://nodejs.org/dist/v24.13.0/node-v24.13.0-linux-x64.tar.gz |
  tar -xz --strip-components=1 -C "$HOME/node"
export PATH="$HOME/node/bin:$HOME/.local/bin:$PATH"

npm install -g --prefix "$HOME/node" pnpm@11.22.0
curl -LsSf https://astral.sh/uv/install.sh | sh
uv python install 3.14

pnpm --dir client install --frozen-lockfile
uv --directory server sync --frozen
