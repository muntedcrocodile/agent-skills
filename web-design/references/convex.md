# Self-hosted Convex setup

Read this only after selecting Convex with the user. The bundled infrastructure
is extracted and generalised from Behaviour's Compose/Nginx deployment. It runs
the backend and its API/HTTP proxy, independently of either React frontend.
It does not create application accounts, install Better Auth, or assume a schema.

## Install the bundle

Prerequisites: Bun, Docker Engine with Compose v2 or later, and an application
with a locked `convex` dependency. Check existing files before copying; merge
intentionally if `infra/convex` already exists. Copy the **contents, including
dotfiles**, of `assets/convex-self-hosted/` into the application's `infra/convex/`.
Keep its `.gitignore` and `.dockerignore`. Do not run the bundle in the skill
source directory, where generated credentials and data would not belong.

From the application root:

```bash
bun add convex
bun infra/convex/configure.ts
docker compose --env-file infra/convex/.env -f infra/convex/compose.yaml up -d --build --wait
```

For an existing project with Convex already locked, use `bun install --frozen-lockfile`
instead of adding it again. The reference project paired Convex JS 1.47.x with
the bundled backend digest. Verify compatibility when changing either; an image
digest is a reproducible baseline, not a promise to remain current forever.

`configure.ts` creates an owner-readable `.env` with a unique Compose project
name and instance identity; repeated runs preserve existing values. It does not
start Docker. Keep `COMPOSE_PROJECT_NAME` stable so updates use the same volume.
Keep the instance name and secret with the data; startup rejects changed identity
on an existing volume. Never regenerate `.env` to repair an existing deployment.

Default host ports are 3210 for API/WebSocket and 3211 for HTTP actions/auth,
bound to loopback through Nginx. Backend ports remain on the container network.
If those host ports are occupied, change `API_PORT`, `HTTP_PORT`, and the matching
origins in `.env` before starting. Run `configure.ts` again to validate edits.
Avoid ambient Compose/instance variables overriding the selected env file.

## Connect the application

Keep the schema/functions in the app's `convex/` directory. Create the schema and
initial functions for the approved product, then use the project dependency's
CLI through the included wrapper:

```bash
bun infra/convex/cli.ts dev --once
bun infra/convex/cli.ts dev
# For repeatable deployment after implementation/typechecking:
bun infra/convex/cli.ts deploy --yes
```

The wrapper must run from the application root. It obtains an admin key privately
from the running Compose backend and supplies an isolated, temporary env file
to the CLI. This prevents a stale Cloud selection in `.env.local` from choosing
the wrong deployment. The key is not printed, passed as a command-line argument,
or saved in browser configuration. Temporary credentials are removed on normal
completion or handled termination; an uncatchable process/host crash may leave
an owner-only directory under the operating system's temporary directory.

Add project script aliases if useful, for example `backend:dev` and
`backend:push`. Commit generated API/types according to the project's Convex
conventions. Do not disable typechecking merely to make deployment succeed.

Set `VITE_CONVEX_URL` to the browser-reachable API origin in the app's frontend
environment. Add `VITE_CONVEX_SITE_URL` only if HTTP actions/auth need it. These
are public URLs. Never place an admin key, instance secret, or auth signing secret
in a `VITE_*` variable or a Vite `define` that reaches the browser.

Mount a `ConvexProvider` with a stable `ConvexReactClient` in the React tree and
use generated query/mutation bindings. For authenticated apps, use the selected
auth integration's provider and enforce identity/permissions in every protected
backend function. For Framework Mode, respect build-time rendering even in SPA
mode; SSR requires deliberate request-scoped auth/client handling.

Convex backend-process configuration and function environment variables are
different. Use `bun infra/convex/cli.ts env ...` to manage an explicit allowlist
of function settings; never upload the entire infrastructure `.env`. Keep any
secret-bearing input/output private. Better Auth requires its component, auth
config, HTTP routes, signing secret, frontend trusted origin, and an account
bootstrap/recovery mechanism. Implement those for the app's actual account model.
Do not copy Behaviour's fixed accounts or passwords.

## Hosting

The bundle does not host frontend files. Build the selected React app with Bun:
serve `dist/` for React + Vite or `build/client/` for React Router SPA mode with
an `index.html` fallback. Configure the app's base path if hosting below `/`.
For SSR, deploy and proxy the framework server instead of serving browser files
as the complete application. Add a project-specific frontend Dockerfile/Compose
service when container hosting is selected, excluding env files from its build
context and supplying only public frontend build variables.

For remote access, use reachable HTTPS origins for frontend, API, and HTTP
actions. `localhost` in a phone's browser refers to the phone, not the server.
Terminate TLS at the approved upstream proxy; the bundled gateway speaks HTTP.
Forward Host and the original HTTPS scheme, and WebSocket upgrade headers with
a long read timeout for the API at **every proxy layer**. Restrict access to the
gateway to that trusted upstream. If the upstream is another container, its own
loopback cannot reach the host's loopback-bound listener: use an appropriate
private network arrangement. Do not expose a dashboard or replace unrelated
proxy/Tailscale configuration. Sharing remains private unless public access was
requested.

## Updates, backup, and restore

Retain the pinned image/configuration revision with backups. Separate development
and production Compose projects and volumes. Deploy schema/functions using the
wrapper; use explicit repeatable migrations for existing records. Test migrations
in development, then take a consistent backup before a production update. A
development-only iteration does not require production backup ceremony.

Commands below run from the application root in Bash. Stop the frontend/other
writers as appropriate. Do not archive a live SQLite database. Use a new backup
directory on every run; protect it because it contains the instance secret and
all application data.

```bash
compose=(docker compose --env-file infra/convex/.env -f infra/convex/compose.yaml)
umask 077
backup_dir="infra/convex/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$(dirname "$backup_dir")"
mkdir "$backup_dir"
"${compose[@]}" stop gateway backend
"${compose[@]}" run --rm -T --no-deps --entrypoint tar backend -C /convex/data -czf - . > "$backup_dir/data.tgz"
cp infra/convex/.env "$backup_dir/deployment.env"
"${compose[@]}" up -d --wait
```

Check every command succeeds; if backup fails, retain the failure and restart
the stopped services before investigating. Copy the protected backup to another
user-controlled location according to the agreed recovery plan. The skill does
not install a backup schedule automatically.

Restore only into a fresh deployment with an **empty** data volume. Copy the
matching source/configuration revision and backed-up `.env` into that deployment,
retaining `INSTANCE_NAME`/`INSTANCE_SECRET`; use a new Compose project name if the
original deployment still exists. Select that deployment in a new `compose` array
and set `backup_dir` to the backup location. Do not start the backend first.

```bash
"${compose[@]}" build backend
"${compose[@]}" run --rm -T --no-deps --entrypoint bash backend -c \
  'set -euo pipefail; test -z "$(ls -A /convex/data)"; tar -xzf - -C /convex/data' < "$backup_dir/data.tgz"
"${compose[@]}" up -d --wait
```

Verify application reads/writes, authentication if present, stored files, and
persistence across restart. Restoring backups into the live volume or deleting
volumes is not an update procedure. Record recovery results and any remaining
hosting prerequisites in the project.

## Official references

- [Convex self-hosting](https://github.com/get-convex/convex-backend/blob/main/self-hosted/README.md)
- [Upstream Compose configuration](https://github.com/get-convex/convex-backend/blob/main/self-hosted/docker/docker-compose.yml)
- [Convex React client](https://docs.convex.dev/client/react)
- [Convex runtime](https://docs.convex.dev/functions/runtimes)
- [Nginx WebSocket proxying](https://nginx.org/en/docs/http/websocket.html)
