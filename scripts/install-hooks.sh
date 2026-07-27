#!/usr/bin/env bash
# Point git at the repo's tracked hooks (hooks/). Run once per clone.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath hooks
chmod +x hooks/* 2>/dev/null || true
echo "✓ git hooks installed (core.hooksPath=hooks)"
echo "  commit-msg: PII scan of the message + enforce <type>: <summary>"
echo "  pre-commit: py_compile staged + crawl-policy guard + PII path/email/denylist guard"
echo "  tip: cp config/pii_terms.example.txt config/pii_terms.txt and add YOUR terms"
