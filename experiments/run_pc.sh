#!/usr/bin/env bash
# Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
# Run experiments on the PC: sync, run SBY, print a status table.
# Usage: ./run_pc.sh <experiment_dir> <file.sby> [tasks...]
# Task status: PASS/FAIL is the engine answer; with 'expect fail' a FAIL is the expected outcome.
set -euo pipefail
HOST="user@10.8.1.14"; KEY="$HOME/.ssh/id_ed25519_homepc"
ROOT="Documents/VS-Code/Claude/open-formal-cdc"
cd "$(dirname "$0")/.."
rsync -az -e "ssh -i $KEY -o ConnectTimeout=8" --exclude build --exclude .git experiments "$HOST:$ROOT/"
dir="$1"; sby="$2"; shift 2
ssh -i "$KEY" -o ConnectTimeout=8 "$HOST" "export PATH=\$HOME/Tools/oss-cad-suite/bin:\$PATH; \
  cd $ROOT/experiments/$dir && rm -rf ../build/$dir && mkdir -p ../build/$dir && \
  timeout 900 sby -f -j 8 --prefix ../build/$dir/${sby%.sby} $sby $* > ../build/$dir/sby.log 2>&1 || true; \
  grep -E 'ERROR' ../build/$dir/sby.log | sed 's/^SBY *[0-9:]* *//' | head -10; \
  for d in ../build/$dir/*/; do n=\$(basename \$d); s=\$(head -1 \$d/status 2>/dev/null || echo '?'); \
    x=\$(grep -hoE '(failed assertion|reached cover statement) [^ ]+ .* step [0-9]+' \$d/logfile.txt 2>/dev/null | sed 's/ at [^ ]* / /' | tr '\n' ';'); \
    printf '%-28s %-12s %s\n' \$n \"\$s\" \"\$x\"; done"
