#!/usr/bin/env bash
# Install the pinned real-browser tooling for tests/browser/ui_checks.cjs and confirm it
# can launch Chromium. Playwright's version is pinned in tests/browser/package.json and
# locked (with integrity hashes) in tests/browser/package-lock.json.
#   scripts/bootstrap_browser.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
cd "$here/tests/browser"
pinned="$(node -p "require('./package.json').dependencies.playwright")"
found="$(node -p "require('playwright/package.json').version" 2>/dev/null || true)"
if [[ "$found" != "$pinned" ]]; then
  echo "installing playwright $pinned (found: ${found:-none})"
  npm ci --ignore-scripts --no-audit --no-fund
fi
if ! node -e "require('playwright').chromium.launch({channel: 'chromium'}).then((b) => b.close())" 2>/dev/null; then
  echo "installing the Chromium build for playwright $pinned"
  npx --no-install playwright install chromium
fi
node -e "require('playwright').chromium.launch({channel: 'chromium'}).then(async (b) => { console.log('playwright', require('playwright/package.json').version, 'chromium', b.version()); await b.close() })"
