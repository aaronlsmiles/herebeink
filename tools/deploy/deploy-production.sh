#!/usr/bin/env bash
# PUBLIC production deploy of the page: herebeink.studionephele.com.
# Run only with the owner's word for this deploy: GO_LIVE=yes tools/deploy/deploy-production.sh
# Needs the gitignored .env.local (REDEPLOY.md): VERCEL_SCOPE, VITE_SCENE_URL, IDENTIFIER_SCAN (the
# scanner script stage.sh runs) and DEPLOY_ENV_OP (a 1Password env file holding a VERCEL_TOKEN reference).
set -euo pipefail
[ "${GO_LIVE:-}" = yes ] || { echo "refusing: a production deploy is public; set GO_LIVE=yes only with the owner's word" >&2; exit 2; }
here="$(cd "$(dirname "$0")/../.." && pwd)"
[ -f "$here/.env.local" ] || { echo "refusing: no .env.local (see REDEPLOY.md)" >&2; exit 2; }
set -a; . "$here/.env.local"; set +a
: "${VERCEL_SCOPE:?set VERCEL_SCOPE in .env.local}"
: "${VITE_SCENE_URL:?set VITE_SCENE_URL in .env.local}"
: "${DEPLOY_ENV_OP:?set DEPLOY_ENV_OP in .env.local to the 1Password env file (see REDEPLOY.md)}"
ENV_OP="$DEPLOY_ENV_OP"
[ -f "$ENV_OP" ] || { echo "refusing: the 1Password env file $ENV_OP is missing (see DEPLOY_ENV_OP in REDEPLOY.md)" >&2; exit 2; }
"$here/tools/deploy/stage.sh"
cd "$here/deploy/production"
# The token reaches vercel only as an environment variable resolved by op run: never a value here, never --token.
run() { op run --env-file="$ENV_OP" -- "$@"; }
[ -f .vercel/project.json ] || run vercel link --yes --scope "$VERCEL_SCOPE" --project herebeink
run vercel deploy --yes --prod --scope "$VERCEL_SCOPE"
