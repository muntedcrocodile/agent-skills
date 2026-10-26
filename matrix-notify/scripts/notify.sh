#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
venv_dir="${MATRIX_NOTIFY_VENV:-${XDG_DATA_HOME:-$HOME/.local/share}/agent-skills/matrix-notify/venv}"
if [[ ! -x "$venv_dir/bin/python" ]]; then
  printf 'Matrix dependencies missing. Run: bash %q/setup.sh\n' "$script_dir" >&2
  exit 1
fi
exec "$venv_dir/bin/python" "$script_dir/matrix_notify.py" "$@"
