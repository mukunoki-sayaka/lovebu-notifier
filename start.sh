# start.sh
#!/usr/bin/env bash
set -euo pipefail

POLL_MS="${POLL_INTERVAL_MS:-800}"
JITTER_MS="${JITTER_MS:-200}"

echo "[start] loop: ${POLL_MS}ms ± ${JITTER_MS}ms"

while :; do
  python check_stock_aio.py || true
  if [ -s needs_confirm.json ]; then
    echo "[trigger] running heavy confirm..."
    python check_stock_playwright.py || true
  fi
  # ジッター付きスリープ
  sleep "$(python - <<'PY'
import os,random
base=int(os.environ.get('POLL_INTERVAL_MS','800'))
jit=int(os.environ.get('JITTER_MS','200'))
print(max(100, base + random.randint(-jit, jit))/1000)
PY
)"
done
