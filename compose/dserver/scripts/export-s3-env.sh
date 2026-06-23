#!/usr/bin/env bash
# export-s3-env.sh — run a command with dtool-s3's per-bucket env vars set.
#
# dtool-s3 reads per-bucket settings from env vars whose NAME embeds the bucket:
#   DTOOL_S3_ENDPOINT_<bucket>, DTOOL_S3_ACCESS_KEY_ID_<bucket>, DTOOL_S3_SECRET_ACCESS_KEY_<bucket>
# (all three are read together — see dtool-s3/dtool_s3/storagebroker.py).
#
# We build them at runtime, not in compose, for TWO reasons:
#   1. docker compose can't interpolate a variable into an environment KEY when base + override
#      files are merged (it emits a literal `$${VAR}`).
#   2. bucket names routinely contain hyphens (e.g. "zhanglab-data", "dtool-bucket"). Shell
#      `export`/assignment REJECT a name with a hyphen ("not a valid identifier"), so we CANNOT
#      `export "DTOOL_S3_ENDPOINT_${S3_BUCKET}=..."`. The `env NAME=VALUE cmd` form has no such
#      restriction (nor do the Docker/Python layers), so we inject the trio via `env` and exec
#      the target command instead of exporting into the current shell.
#
# Usage:  export-s3-env.sh <command> [args...]
#   e.g.  export-s3-env.sh gunicorn ...
#         export-s3-env.sh flask base_uri index s3://<bucket>
set -o errexit
set -o nounset

if [ -n "${S3_BUCKET:-}" ]; then
    exec env \
        "DTOOL_S3_ENDPOINT_${S3_BUCKET}=${S3_ENDPOINT:?S3_ENDPOINT must be set when S3_BUCKET is set}" \
        "DTOOL_S3_ACCESS_KEY_ID_${S3_BUCKET}=${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID must be set when S3_BUCKET is set}" \
        "DTOOL_S3_SECRET_ACCESS_KEY_${S3_BUCKET}=${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY must be set when S3_BUCKET is set}" \
        "$@"
else
    exec "$@"
fi
