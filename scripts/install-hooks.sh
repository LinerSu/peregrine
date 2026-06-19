#!/usr/bin/env bash
# Point git at the repo's tracked hooks (hooks/). Run once per clone.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath hooks
chmod +x hooks/* 2>/dev/null || true
echo "✓ git hooks installed (core.hooksPath=hooks)"
echo "  commit-msg: enforce <type>: <summary>"
echo "  pre-commit: py_compile staged + crawl-policy guard"
