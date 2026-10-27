#!/usr/bin/env bash
set -euo pipefail
cd /convex
: "${INSTANCE_NAME:?Configure the instance first}"
: "${INSTANCE_SECRET:?Configure the instance first}"
# Never start existing data with a newly generated or accidentally changed identity.
for field in instance_name instance_secret; do
  variable=${field^^}
  stored="/convex/data/credentials/$field"
  if [[ -s "$stored" && "$(cat "$stored")" != "${!variable}" ]]; then
    echo "Configured $variable differs from this volume. Restore its original .env." >&2
    exit 1
  fi
done
exec ./run_backend.sh "$@"
