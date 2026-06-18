# CLAUDE.md — dserver-development-stack

Guidance for Claude Code working in this repository. This is a **Docker Compose
development stack** that wires together `dserver` (a Flask REST API for dtool dataset
metadata) and the `dtool-lookup-webapp` Vue.js frontend, plus all their backing services
and plugins, from local source checkouts (git submodules) installed in editable mode.

> There is also a `README.md` aimed at end users. It is partly **out of date** — see
> "Known README discrepancies" at the bottom before trusting it. This file reflects what
> the code actually does.

> **No HTTPS layer on `main`.** `main` is the plain dev stack — plaintext HTTP on
> localhost, debug server, public MinIO bucket. A separate HTTPS deployment layer (Caddy
> TLS proxy with Let's Encrypt/ACME, gunicorn, and MinIO over TLS) lives on the
> **`acme-deployment`** / **`zhanglab-data`** branches, **not** on `main`. Work from those
> branches if you need a TLS-terminated, internet-facing deployment.

## What gets deployed

`docker compose up -d` brings up these services (defined in `docker-compose.yml`):

| Service | Image / build | Port(s) | Role |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | SQL store for dserver admin metadata (users, base URIs, dataset registry) |
| `mongo` | `mongo:7` | 27017 | Backend for the search & retrieve plugins and dependency graph |
| `minio` | `minio/minio` | 9000 (API), 9001 (console) | S3-compatible object storage for dtool datasets |
| `minio-init` | `minio/mc` | — | One-shot: creates public bucket `dtool-bucket` |
| `dserver-build-venv` | `compose/dserver/Dockerfile` | — | One-shot: builds the Python venv into the `dserver_venv` volume |
| `dserver` | `dserver_image` (same Dockerfile) | 5000 | The Flask REST API + plugins; runs `flask run --debug` |
| `webapp` | `compose/webapp/Dockerfile` | 8080 | Vue.js dev server (hot-reload) |
| `index-s3` | `dserver_image` | — | Profile `index` only: runs `flask base_uri index s3://dtool-bucket` |

Named volumes: `postgres_data`, `mongo_data`, `minio_data`, `dserver_venv`. All services
share the `dserver_net` bridge network.

### Credentials & endpoints (development defaults)

- Postgres / Mongo: user `dserver`, password `dserver_secret`, db `dserver`.
- MinIO: `minioadmin` / `minioadmin`; bucket `dtool-bucket` (public).
- dserver API: http://localhost:5000 — health at `/config/health`, Swagger at `/doc/swagger`.
- Webapp: http://127.0.0.1:8080 (use `127.0.0.1`, not `localhost` — see OAuth2 note).
- Token endpoint: `POST /auth/token` (provided by the OAuth2 token generator plugin).

## Deploying locally — the real flow

### 0. Prerequisites
- **Docker + Docker Compose v2.** Note: not every host has Docker installed — the stack
  is meant for a developer machine or a server with a container runtime. (`docker` /
  `docker compose` are absent from a stock minimal Ubuntu install.)
- **GitHub access for submodules.** All submodule URLs in `.gitmodules` use the public
  `https://github.com/` form, so `git submodule update --init` works without a GitHub SSH
  key (the repos are public).

### 1. Initialize submodules — REQUIRED
The 13 submodules are **not checked out** in a fresh clone (the directories are empty
placeholders). Nothing builds until they are populated:

```bash
git submodule update --init --recursive
# or clone with:  git clone --recursive <url>
```

Verify with `git submodule status` — initialized entries lose the leading `-`.

### 2. (Optional) OAuth2 credentials
Authentication is handled by `dserver-token-generator-plugin-oauth2`, configured for
**ORCID** in `docker-compose.yml`. To actually log in through the webapp you need ORCID
client credentials:

```bash
cp .env.template .env          # then fill in:
#   OAUTH2_CLIENT_ID=...
#   OAUTH2_CLIENT_SECRET=...
```

Get them from https://orcid.org/developer-tools (or the sandbox). The stack still starts
without these, but the OAuth2 login flow won't complete. For scripted/admin access you
can mint a JWT directly from the generated key instead (see "Indexing" below) — no ORCID
round-trip needed. See "Authentication" below for the full flow and user provisioning.

### 3. Bring it up
```bash
docker compose up -d
docker compose ps          # wait for healthchecks
docker compose logs -f dserver
```

First run is slow: it builds two images, creates the venv volume (installs ~9 packages,
several from local source via `pip install -e`), and the webapp image builds
`dserver-client-js` then `npm install`s the Vue app. On a small (1-vCPU / 2-GB) box this
will strain RAM and take a while.

### 4. /etc/hosts (for accessing datasets from the host)
Datasets are referenced by their internal S3 hostname. To make those URLs resolve from
the host machine, add:
```
127.0.0.1 dserver-minio-alias
127.0.0.1 minio
```
URL rewriting is intentionally avoided because it breaks S3 request signatures — the hosts
entries are the supported workaround.

## How startup works (so you can debug it)

- **`compose/dserver/Dockerfile`** — `python:3.12-slim` + `curl git gcc libpq-dev
  python3-dev`, non-root user `dserver` (uid 1000). `ENTRYPOINT` =
  `scripts/entrypoint.sh`, which just `source /venv/bin/activate` then `exec "$@"`.
- **`scripts/make-venv.sh`** (run by `dserver-build-venv`) — creates `/venv`, installs
  editable: `dtoolcore`, `dtool-s3`, `dservercore`, `dserver-retrieve-plugin-mongo`,
  `dserver-dependency-graph-plugin`, `dserver-signed-url-plugin`,
  `dserver-token-generator-plugin-oauth2`; from PyPI: `dtool-cli`, `dtool-info`,
  `dserver-search-plugin-mongo`, plus `gunicorn psycopg2-binary PyJWT requests authlib
  httpx python-dotenv`. Writes a `/venv/VENV-READY` sentinel and **skips rebuild if it
  exists** — see "rebuilding the venv".
- **`scripts/start-dserver.sh`** (the `dserver` command) — generates an RSA JWT keypair in
  `compose/dserver/jwt/` if missing, runs `flask db init/migrate/upgrade`, creates the
  `admin` user (`flask user add --is_admin admin`), registers base URI
  `s3://dtool-bucket`, grants `admin` search+register permission on it, then
  `flask run --host 0.0.0.0 --port 5000 --debug`.
- **`compose/webapp/Dockerfile`** — builds `dserver-client-js` first, rewrites the webapp's
  `file:../../dserver-client-js` dependency to the in-image path, `npm install`, copies
  source, runs `npm run serve`. Note the webapp source lives in a **doubly-nested** path:
  `dtool-lookup-webapp/dtool-lookup-webapp/` (submodule dir contains a subdir of the same
  name); `src/` and `public/` are bind-mounted for hot-reload.

JWT keys (`compose/dserver/jwt/jwt_key{,.pub}`) are runtime-generated and git-ignored.

## Authentication (ORCID OAuth2)

Authentication is handled by `dserver-token-generator-plugin-oauth2`, configured for
**ORCID** in `docker-compose.yml`. Flow: webapp → `GET /auth/login` → ORCID →
`GET /auth/callback` → dserver mints an RS256 JWT → webapp (token in the redirect).

- **Credentials:** `OAUTH2_CLIENT_ID`/`OAUTH2_CLIENT_SECRET` live in `.env` (git-ignored).
  Register an app at orcid.org (or sandbox.orcid.org) for the Public API. The stack still
  starts without these, but the login flow won't complete.
- **Redirect URI to register at ORCID:** `OAUTH2_BASE_URL` + `/auth/callback` (must match
  exactly, or ORCID rejects the request). On the local stack `OAUTH2_BASE_URL` defaults to
  `http://127.0.0.1:5000`, so the URI is `http://127.0.0.1:5000/auth/callback`. ORCID never
  fetches it — only the user's browser does — so a localhost value works for dev.
- **The username IS the ORCID iD.** A new ORCID user authenticates but gets
  `401 Unauthorized` on API calls until **provisioned** — this is the access gate:
  ```
  docker compose exec dserver bash -lc 'source /venv/bin/activate && \
    flask user add <ORCID-iD>            # add --is_admin for administrators
    flask user search_permission <ORCID-iD> s3://dtool-bucket
    flask user register_permission <ORCID-iD> s3://dtool-bucket'
  ```
  Provisioned users persist in Postgres.
- The login page shows only the ORCID button (`VUE_APP_SHOW_USERNAME_PASSWORD_FORM=false`);
  the username/password form is dead with this plugin. The `admin` DB user remains for
  CLI/scripted JWTs (see `indexall.sh`).
- **Webapp-side toggle:** `VUE_APP_AUTH_ENABLED` (default `"true"` in `docker-compose.yml`).
  Setting it to `"false"` hides the SignIn screen and lets the webapp call the API without
  an `Authorization` header. This is a frontend switch only — it **must** be paired with
  dserver running in its own no-auth mode, otherwise every request returns 401. The
  webapp's `/users/<username>/summary` call was moved to `/me/summary` so the panel works
  in both modes without needing a username from a JWT.
- A dev-only alternative that accepts any username/password (`dserver-dummy-token-generator`,
  livMatS/dserver-development-stack PR #2) exists but is **not** used here — it is
  unauthenticated, so only acceptable behind a VPN/internal firewall.

## Common operations

```bash
# Logs
docker compose logs -f                 # all
docker compose logs -f dserver         # one service

# Stop / teardown
docker compose down                    # keep data volumes
docker compose down -v                 # also wipe postgres/mongo/minio/venv

# Rebuild the venv after changing dependencies (the VENV-READY sentinel blocks reuse):
docker compose down
docker volume rm dserver-development-stack_dserver_venv
docker compose up -d

# Get an admin JWT from the running API
TOKEN=$(curl -s -X POST http://localhost:5000/auth/token \
  -H "Content-Type: application/json" -d '{"username":"admin"}' | jq -r '.token')
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/config/info
```

### Indexing datasets into dserver
Three equivalent paths exist; pick whichever fits:

```bash
# A) Compose one-shot service (note the profile is `index`, the service `index-s3`):
docker compose --profile index up index-s3
#    (internally: flask base_uri index s3://dtool-bucket)

# B) Host-side helper — mints a JWT straight from the private key, then calls the REST API:
./indexall.sh
#    requires host python with: pyjwt, dtoolcore, requests; reads JWT_PRIVATE_KEY_FILE
#    (defaults to compose/dserver/jwt/jwt_key) and calls tools/indexall.py

# C) Inside the dserver container:
docker compose exec dserver flask base_uri index s3://dtool-bucket
```

`tools/indexall.py` walks a base URI via the dtool storage broker, skips proto (unfrozen)
datasets, and `PUT /uris/<url-encoded-uri>`s each frozen dataset's metadata.

### Pushing datasets from the host
Install `dtool-s3`, copy `dtool.json` to `~/.config/dtool/dtool.json` (it points at
`http://localhost:9000` with the `minioadmin` creds), then `dtool create / freeze /
cp <ds> s3://dtool-bucket/`. To go through dserver instead of raw S3, install
`dtool-dserver` and use `dserver://localhost:5000/...` URIs with a `DSERVER_TOKEN`.

## Database migrations
Alembic config lives in `migrations/` (`alembic.ini`, `env.py`). The one committed
revision (`60ebaabea8a4`) creates the `base_uri`, `user`, and `dataset` tables.
`migrations/versions/*.py` is git-ignored except that baseline. `start-dserver.sh` runs
`flask db init/migrate/upgrade` on every boot (the first two are `|| true`).

## Submodules (13)
Source: `jic-dtool/*` (upstream dtool/dserver) and `livMatS/*` (lab forks & plugins).
Core: `dtoolcore`, `dtool` (CLI/meta), `dtool-s3`, `dtool-dserver`, `dservercore`.
Plugins: `dserver-search-plugin-mongo`, `dserver-retrieve-plugin-mongo`,
`dserver-dependency-graph-plugin`, `dserver-signed-url-plugin`,
`dserver-notification-plugin`, `dserver-token-generator-plugin-oauth2`.
Frontend: `dtool-lookup-webapp`, `dserver-client-js`.

(Not every submodule is installed by `make-venv.sh` — e.g. `dtool`,
`dserver-notification-plugin`, and `dtool-dserver` are present as checkouts but not in the
venv install list. Add them there if you need them in the running server.)

## Known README discrepancies
`README.md` predates the OAuth2 migration. When following it, substitute:
- **Auth:** README describes a "dummy token generator" accepting any user/password on a
  separate service at port **5001**. The live stack uses the **OAuth2/ORCID** plugin
  integrated into dserver at `/auth/token`. The leftover
  `compose/dserver/scripts/start-token-generator.sh` (a standalone Flask app on 5001) is
  **not wired into `docker-compose.yml`** — ignore it.
- **Indexing:** README says `--profile indexer` + `/scripts/index-datasets.sh` /
  `create-test-dataset.sh`. The real profile is `index` and service `index-s3`. The
  `index-datasets.sh` script does not exist; `create-test-dataset.sh` does and creates a
  sample dataset, but no compose service invokes it (run it manually inside a container).
- **`dtool-azure` / `dtool-cli`** appear in the README submodule table but are not in
  `.gitmodules`.

## Conventions for this repo
- Don't commit or push unless asked; branch first.
- Treat `docker-compose.yml` and the `compose/dserver/scripts/*.sh` as the source of truth
  over `README.md`.
- This is a **development** stack: debug mode on, wildcard CORS, hard-coded secrets
  (`SECRET_KEY`, DB passwords, `minioadmin`). Never reuse these settings for anything
  exposed.
