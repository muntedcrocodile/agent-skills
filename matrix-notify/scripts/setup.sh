#!/usr/bin/env bash
set -euo pipefail
skill_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
venv_dir="${MATRIX_NOTIFY_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/agent-skills/matrix-notify/venv}"
if command -v uv >/dev/null 2>&1; then
  if [[ ! -x "$venv_dir/bin/python" ]]; then
    uv venv "$venv_dir"
  fi
  uv pip install --python "$venv_dir/bin/python" -r "$skill_dir/requirements.txt"
else
  if [[ ! -x "$venv_dir/bin/python" ]]; then
    python3 -m venv "$venv_dir"
  fi
  "$venv_dir/bin/python" -m pip install -r "$skill_dir/requirements.txt"
fi
printf 'Matrix dependencies installed. Run bash %q/scripts/notify.sh init next.\n' "$skill_dir"
