# CLAUDE.md — dserver-development-stack

Guidance for Claude Code working in this repository. This is a **Docker Compose
development stack** that wires together `dserver` (a Flask REST API for dtool dataset
metadata) and the `dtool-lookup-webapp` Vue.js frontend, plus all their backing services
and plugins, from local source checkouts (git submodules) installed in editable mode.

> There is also a `README.md` aimed at end users. It is partly **out of date** — see
> "Known README discrepancies" at the bottom before trusting it. This file reflects what
> the code actually does.

> **Deployment model:** this file is the **shared base** recipe (branch
> `https-deploy-base`). Concrete HTTPS deployments are *site branches* that build on it and
> add only their site-specific pieces (see `DEPLOYMENT-MODEL.md`):
> - **`zhanglab-data`** — Caddy layer4 + a **remote** MinIO (lab Synology over WireGuard),
>   ORCID-only auth.
> - **`acme-deployment`** — a self-contained public demo: Caddy + cert-sync + **local**
>   MinIO native TLS, username/password (LDAP) login.
>
> If you are on a site branch, that branch's `CLAUDE.md` appends a
> **`## HTTPS deployment recipe (this site)`** section at the END of this file with the
> concrete topology, files, certs, bring-up and gotchas. The shared sections below
> (the plain dev stack, auth mechanics, operations, and the cross-site HTTPS concepts)
> apply underneath every site.

## What gets deployed

`docker compose up -d` brings up these services (defined in `docker-compose.yml`):

| Service | Image / build | Port(s) | Role |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | 5432 | SQL store for dserver admin metadata (users, base URIs, dataset registry) |
| `mongo` | `mongo:7` | 27017 | Backend for the search & retrieve plugins and dependency graph |
| `minio` | `minio/minio` | 9000 (API), 9001 (console) | S3-compatible object storage for dtool datasets (behind the `local-minio` profile) |
| `minio-init` | `minio/mc` | — | One-shot: creates the bucket (behind the `local-minio` profile) |
| `ldap` | `osixia/openldap` | 389 | Dev directory for username/password login (behind the `ldap` profile) |
| `dserver-build-venv` | `compose/dserver/Dockerfile` | — | One-shot: builds the Python venv into the `dserver_venv` volume |
| `dserver` | `dserver_image` (same Dockerfile) | 5000 | The Flask REST API + plugins |
| `webapp` | `compose/webapp/Dockerfile` | 8080 | Vue.js dev server (hot-reload) |
| `index-s3` | `dserver_image` | — | Profile `index` only: runs `flask base_uri index s3://${S3_BUCKET}` |

Named volumes: `postgres_data`, `mongo_data`, `minio_data`, `dserver_venv`. All services
share the `dserver_net` bridge network. `minio`/`minio-init`/`ldap` are gated behind compose
**profiles** (`local-minio`, `ldap`) so a plain `docker compose up` starts only the core; a
site enables what it needs via `COMPOSE_PROFILES` (see its recipe).

### Credentials & endpoints (development defaults)

- Postgres / Mongo: user `dserver`, password `dserver_secret`, db `dserver`.
- MinIO: `minioadmin` / `minioadmin`; bucket `${S3_BUCKET}`.
- dserver API: http://localhost:5000 — health at `/config/health`, Swagger at `/doc/swagger`.
- Webapp: http://127.0.0.1:8080 (use `127.0.0.1`, not `localhost` — see OAuth2 note).
- Token endpoints: ORCID OAuth2 under `/auth/oauth2/*`; username/password (LDAP) at
  `POST /auth/ldap/token` (see "Authentication").

## Deploying locally — the real flow

### 0. Prerequisites
- **Docker + Docker Compose v2.** Note: not every host has Docker installed — the stack
  is meant for a developer machine or a server with a container runtime. (`docker` /
  `docker compose` are absent from a stock minimal Ubuntu install.)
- **GitHub access for submodules.** All submodule URLs in `.gitmodules` use the public
  `https://github.com/` form, so `git submodule update --init` works without a GitHub SSH
  key (the repos are public).

### 1. Initialize submodules — REQUIRED
The submodules are **not checked out** in a fresh clone (the directories are empty
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

First run is slow: it builds two images, creates the venv volume (installs the editable
packages from local source via `pip install -e`), and the webapp image builds
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
  `dserver-dependency-graph-plugin`, `dserver-direct-mongo-plugin`,
  `dserver-signed-url-plugin`, `dserver-token-generator-plugin-oauth2` (and
  `dserver-token-generator-plugin-ldap` **only when `INSTALL_LDAP_PLUGIN=true`**); from
  PyPI: `dtool-cli`, `dtool-info`, `dserver-search-plugin-mongo`, plus
  `gunicorn psycopg2-binary PyJWT requests authlib httpx python-dotenv ldap3`. Pins
  `setuptools<81` (keeps `pkg_resources` for `dtool-cli`) and adds
  `dtool-create`/`dtool-symlink`/`dtool-http`/`ruamel.yaml` (create/freeze/cp). Writes a
  `/venv/VENV-READY` sentinel and **skips rebuild if it exists** — see "rebuilding the venv".
- **`scripts/start-dserver.sh`** (the dev `dserver` command) — generates an RSA JWT keypair
  in `compose/dserver/jwt/` if missing, runs `flask db init/migrate/upgrade`, creates the
  `admin` user (`flask user add --is_admin admin`), registers base URI `s3://${S3_BUCKET}`,
  grants `admin` search+register permission on it, then `flask run --host 0.0.0.0 --port
  5000 --debug`. (HTTPS sites swap this for `start-dserver-gunicorn.sh` — see the site
  recipe.)
- **`compose/webapp/Dockerfile`** — builds `dserver-client-js` first, rewrites the webapp's
  `file:../../dserver-client-js` dependency to the in-image path, `npm install`, copies
  source, runs `npm run serve`. Note the webapp source lives in a **doubly-nested** path:
  `dtool-lookup-webapp/dtool-lookup-webapp/` (submodule dir contains a subdir of the same
  name); `src/` and `public/` are bind-mounted for hot-reload. The webapp image bakes in the
  built `dserver-client` + `node_modules`, so after advancing the `dtool-lookup-webapp` /
  `dserver-client-js` submodules you must **rebuild the webapp image** (`docker compose
  build webapp`) or the dev server compiles new `src/` against a stale client (symptoms:
  `Module not found: d3`, `dserver-client has no exported member …`).

JWT keys (`compose/dserver/jwt/jwt_key{,.pub}`) are runtime-generated and git-ignored.

## Authentication

Two token generators run side by side as `dservercore.extension` plugins (dservercore
registers every extension blueprint, so multiple coexist as long as their URL prefixes
differ). Both mint RS256 JWTs signed with the same key dserver verifies; both gate access
on dserver's own user table (`sub` claim must be a provisioned user, else 401 on every
route). Which login methods are actually offered is a per-site choice (see the site recipe).

### ORCID OAuth2 — `dserver-token-generator-plugin-oauth2` (prefix `/auth/oauth2`)

Flow: webapp → `GET /auth/oauth2/login` → ORCID → `GET /auth/oauth2/callback` → dserver
mints a JWT → webapp (token in the redirect fragment).

- **Credentials:** `OAUTH2_CLIENT_ID`/`OAUTH2_CLIENT_SECRET` live in `.env` (git-ignored).
  Register an app at orcid.org (or sandbox.orcid.org) for the Public API. The stack still
  starts without these, but the login flow won't complete.
- **Redirect URI to register at ORCID:** `OAUTH2_REDIRECT_URI` — on the local stack
  `http://127.0.0.1:5000/auth/oauth2/callback` (must match exactly). ORCID never fetches it
  — only the user's browser does — so a localhost value works for dev. (Note: the plugin
  moved from `/auth` to `/auth/oauth2` so the LDAP plugin can own `/auth/ldap`; the webapp's
  OAuth2 URL is set via `VUE_APP_OAUTH2_LOGIN_URL`.)
- **The username IS the ORCID iD.** A new ORCID user authenticates but gets `401` until
  **provisioned** (see the `flask user add` / `*_permission` commands below).

### Username/password via LDAP — `dserver-token-generator-plugin-ldap` (prefix `/auth/ldap`)

The simple login. The webapp's username/password form POSTs `{username,password}` to
`POST /auth/ldap/token` (`VUE_APP_DTOOL_LOOKUP_SERVER_TOKEN_GENERATOR_URL`); the plugin
binds against LDAP, and on success mints a JWT. **The plugin is installed into the venv only
when `INSTALL_LDAP_PLUGIN=true`** (base `make-venv.sh` gate) and the `ldap` service runs only
under the `ldap` profile — a site that authenticates via ORCID only leaves both off, so no
`/auth/ldap` blueprint exists.

- **Bundled dev directory:** the `ldap` service (osixia/openldap, seeded via
  `compose/ldap/bootstrap/*.ldif`) is seeded with
  **`testuser` / `test_password`**. Point `LDAP_URI` (+ `LDAP_BIND_DN`, `LDAP_USER_BASE_DN`,
  `LDAP_USER_FILTER`, …) at an external/corporate LDAP for real use; add users there, not in
  dserver. LDAP config lives in the `dserver` service env in `docker-compose.yml`; see the
  plugin's `README.md` for all knobs (search-then-bind vs `LDAP_USER_DN_TEMPLATE`, TLS, etc.).
- **Auto-provisioning:** with `LDAP_AUTO_PROVISION_USERS=true`, a first successful LDAP login
  creates the dserver user and grants search/register on `LDAP_DEFAULT_BASE_URIS` — so LDAP
  users work with zero manual steps. Set it to `false` to require an admin to `flask user
  add` them instead.

### User provisioning (both methods) & toggles

```
docker compose exec dserver bash -lc 'source /venv/bin/activate && \
  flask user add <username>            # add --is_admin for administrators
  flask user search_permission <username> s3://${S3_BUCKET}
  flask user register_permission <username> s3://${S3_BUCKET}'
```
Provisioned users persist in Postgres. The `admin` DB user remains for CLI/scripted JWTs
(see `indexall.sh`).

- **Webapp-side toggle:** `VUE_APP_AUTH_ENABLED` (default `"true"`). Setting it to `"false"`
  hides the SignIn screen and lets the webapp call the API without an `Authorization` header
  — a frontend switch only; **must** be paired with dserver in its own no-auth mode or every
  request returns 401. The webapp's `/users/<username>/summary` call was moved to
  `/me/summary` so the panel works in both modes.
- `VUE_APP_SHOW_USERNAME_PASSWORD_FORM` shows the form; `VUE_APP_OAUTH2_ENABLED` shows the
  ORCID button. Either or both can be enabled — a per-site choice.
- Historically a `dserver-dummy-token-generator` (any username/password, no validation) and a
  standalone `compose/dserver/scripts/start-token-generator.sh` provided simple login; the
  LDAP plugin replaces them with real credential validation.

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

# Get an admin JWT. The OAuth2 plugin does NOT mint username-only tokens at
# POST /auth/token (that was the old dummy generator — it now returns
# "Missing api_key or username"). Mint one from the private key instead, the
# same way indexall.sh does (requires host python with PyJWT):
TOKEN=$(python3 - <<'PY'
import jwt
from datetime import datetime, timedelta, timezone
key = open('compose/dserver/jwt/jwt_key').read()
print(jwt.encode({'sub': 'admin', 'iat': datetime.now(timezone.utc),
                  'exp': datetime.now(timezone.utc) + timedelta(hours=1),
                  'fresh': True}, key, algorithm='RS256'))
PY
)
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/config/info
```

### Indexing datasets into dserver
Three equivalent paths exist; pick whichever fits:

```bash
# A) Compose one-shot service (note the profile is `index`, the service `index-s3`):
docker compose --profile index up index-s3
#    (internally: flask base_uri index s3://${S3_BUCKET})

# B) Host-side helper — mints a JWT straight from the private key, then calls the REST API:
./indexall.sh
#    requires host python with: pyjwt, dtoolcore, requests; reads JWT_PRIVATE_KEY_FILE
#    (defaults to compose/dserver/jwt/jwt_key) and calls tools/indexall.py

# C) Inside the dserver container:
docker compose exec dserver flask base_uri index s3://${S3_BUCKET}
```

`tools/indexall.py` walks a base URI via the dtool storage broker, skips proto (unfrozen)
datasets, and `PUT /uris/<url-encoded-uri>`s each frozen dataset's metadata.

### Pushing datasets from the host
Install `dtool-s3`, copy `dtool.json` to `~/.config/dtool/dtool.json` (it points at
`http://localhost:9000` with the `minioadmin` creds), then `dtool create / freeze /
cp <ds> s3://${S3_BUCKET}/`. To go through dserver instead of raw S3, install
`dtool-dserver` and use `dserver://localhost:5000/...` URIs with a `DSERVER_TOKEN`.

## Database migrations
Alembic config lives in `migrations/` (`alembic.ini`, `env.py`). The one committed
revision (`60ebaabea8a4`) creates the `base_uri`, `user`, and `dataset` tables.
`migrations/versions/*.py` is git-ignored except that baseline. `start-dserver.sh` runs
`flask db init/migrate/upgrade` on every boot (the first two are `|| true`).

## Submodules
Source: `jic-dtool/*` (upstream dtool/dserver) and `livMatS/*` (lab forks & plugins).
Core: `dtoolcore`, `dtool` (CLI/meta), `dtool-s3`, `dtool-dserver`, `dservercore`.
Plugins: `dserver-search-plugin-mongo`, `dserver-retrieve-plugin-mongo`,
`dserver-dependency-graph-plugin`, `dserver-direct-mongo-plugin`,
`dserver-signed-url-plugin`, `dserver-notification-plugin`,
`dserver-token-generator-plugin-oauth2`, `dserver-token-generator-plugin-ldap`.
Frontend: `dtool-lookup-webapp`, `dserver-client-js`.

(Not every submodule is installed by `make-venv.sh` — e.g. `dtool`,
`dserver-notification-plugin`, and `dtool-dserver` are present as checkouts but not in the
venv install list. Add them there if you need them in the running server.)

### Submodules over HTTPS on hosts with no GitHub SSH key

`.gitmodules` uses `git@github.com:` SSH URLs. If the host has no GitHub SSH key, all
submodules are public, so init them over HTTPS without modifying `.gitmodules`:
```bash
git -c url."https://github.com/".insteadOf="git@github.com:" submodule update --init --recursive
```

## HTTPS deployment — shared concepts

These apply to **every** site recipe; the site sections below assume them.

### The base + per-site overlay model
`docker compose` auto-merges `docker-compose.override.yml` on top of `docker-compose.yml`.
The base ships the parameterized `docker-compose.yml` + shared scripts and **no** override /
`caddy` service; each site branch ships its own `docker-compose.override.yml` + Caddy config
+ `.env`. The S3 backend is driven by `${S3_BUCKET}` + `S3_ENDPOINT`/`S3_ACCESS_KEY_ID`/
`S3_SECRET_ACCESS_KEY`; `compose/dserver/scripts/export-s3-env.sh` assembles dtool-s3's
bucket-named trio (`DTOOL_S3_ENDPOINT_<bucket>` etc.) from those at runtime — because
**compose cannot interpolate a variable into an environment KEY** (`DTOOL_S3_ENDPOINT_${S3_BUCKET}:`
renders literally). See `DEPLOYMENT-MODEL.md` for the full structure.

### Why gunicorn + `SCRIPT_NAME=/lookup`
Single `/lookup` prefix (modelled on `dserver-minimal`'s single-container) ⇒ the proxy
needs two rules, not an enumeration of dservercore's ~13 blueprints. Gunicorn applies
`SCRIPT_NAME=/lookup` to the WSGI environ: `/lookup/config/health` splits into
`SCRIPT_NAME=/lookup` + `PATH_INFO=/config/health`, so routing matches and
`url_for(_external=True)` emits correct `https://…/lookup/…`. `flask run` (Werkzeug) does
**not** honour `SCRIPT_NAME` the same way. Caddy uses `handle /lookup*` (not `handle_path`)
to keep the prefix; the healthcheck probes `/lookup/config/health`. HTTPS sites run
`compose/dserver/scripts/start-dserver-gunicorn.sh` (same prep as `start-dserver.sh`, then
`exec gunicorn`), bind-mounted via `/app` so no image rebuild is needed.

### Why MinIO (:9000) is NOT fronted by an HTTP reverse proxy
Caddy (Go `net/http`) **canonicalises response header names** — MinIO's lowercase
`x-amz-meta-type` becomes `X-Amz-Meta-Type`. botocore slices the metadata key *after* the
`x-amz-meta-` prefix **without lowercasing**, so proxied reads come back keyed `Type`/
`Handle` and dtool-s3's lowercase lookups `KeyError` (`'type'`). The body is intact, so
browser downloads through a proxy are fine, but dserver's **server-side reads** (needed to
mint presigned URLs) break. Every site therefore keeps Caddy's HTTP proxy out of the S3
path and terminates :9000 TLS another way — **how** is the main site-specific choice
(`zhanglab-data`: Caddy layer4 raw-TCP to a remote MinIO; `acme-deployment`: local MinIO's
own native TLS fed by a cert-sync sidecar). See the site recipe.

### `SIGNED_URL_HOST_REWRITE` — leave it unset
The signed-url plugin's `SIGNED_URL_HOST_REWRITE` is a **post-signing string replace**
(`__init__.py:222`) and breaks SigV4 (which signs the Host). Instead, every site signs for
the real public host by pointing dserver's S3 endpoint at `https://${DEPLOY_FQDN}:9000` and
giving the relevant in-network service a Docker **network alias = `${DEPLOY_FQDN}`**, so
dserver reads **and** signs against the same `host:port` the browser uses (consistent SigV4
Host). Path-style addressing throughout (`…:9000/<bucket>/<key>`).

## Future: institutional SSO (exploration, not yet implemented)

Goal: let users authenticate with institutional credentials instead of (or alongside)
ORCID. The available plugin is **OIDC/OAuth2-only**; SAML needs the separate SAML plugin.
Two viable paths, depending on what your IdP speaks:

- **Path A — OIDC via Microsoft Entra ID (easiest, config-only).** If your institution's
  identity provider includes a Microsoft 365 / Entra ID tenant and IT will let you
  register an app, configure the existing OAuth2 plugin like ORCID/Google:
  ```
  OAUTH2_AUTHORIZATION_URL = https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/authorize
  OAUTH2_TOKEN_URL         = https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token
  OAUTH2_USERINFO_URL      = https://graph.microsoft.com/oidc/userinfo
  OAUTH2_SCOPE             = openid email profile
  # register redirect URI: https://$DEPLOY_FQDN/lookup/auth/oauth2/callback
  ```
  Tolerant of a no-public-DNS setup (Entra doesn't fetch the redirect URI; the browser
  does). Nuance: the username (UPN) is usually in the **id_token**, which the plugin
  doesn't decode — it reads the token response + `/oidc/userinfo`. Map username to
  `email`/`sub`, or add a few lines to read `preferred_username` from the id_token.

- **Path B — SAML via a Shibboleth / academic federation IdP.** Needed for standard
  attribute release (`eduPersonPrincipalName`, `mail`, affiliation) through federations
  such as **GakuNin** (Japan, NII), **eduGAIN** (international), or InCommon (US). The
  OAuth2 plugin can't do SAML; two ways to add it:
  - **Native SAML SP plugin (chosen direction; drafted).** A `dserver-token-generator-plugin-saml`
    `dservercore.extension` (pysaml2) that makes dserver a SAML SP directly —
    `/login` (AuthnRequest), `/acs`, `/metadata`, `/sls` — and mints the same dserver JWT.
    Prefix is configurable (`SAML_URL_PREFIX`, default `/saml` to coexist with OAuth2's
    `/auth`). Pure logic (attribute map, JWT) is unit-tested; the live flow is untested
    pending IdP metadata + SP registration. Parked on the **`saml-plugin`** branch (off
    `main`) and **not yet wired into the stack** (needs `xmlsec1` in the Dockerfile + an
    install line in `make-venv.sh`); see its `README.md` there.
  - **Proxy alternative:** run **SATOSA** (SAML2 SP ↔ OIDC OP) and point the existing
    OAuth2 plugin at it — no dserver code, but an extra container.
  - **Prerequisites (either way):** register dserver as an SP with the federation
    operator + your institutional IdP admin (metadata exchange + attribute release) and
    **publicly reachable SP endpoints**.

**Gating step:** ask your institutional IT whether a self-hosted service may register an
**Entra ID OIDC app** (→ Path A) or must integrate as a **SAML SP** in your federation
(→ Path B). The provisioning model is unchanged from ORCID: the IdP-supplied identifier
(Entra UPN / SAML ePPN) becomes the dserver username and needs a one-time
`flask user add` to gain permissions.

Refs: GakuNin <https://www.gakunin.jp/en>; SATOSA
<https://github.com/IdentityPython/SATOSA> (saml2-to-oidc).

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

## HTTPS deployment recipe (this site: zhanglab-data)

> Site overlay on top of the shared base above. Serves the **webapp on
> `https://${DEPLOY_FQDN}/`** and the **dserver API under `/lookup`** (both on :443 via
> Caddy), and **S3 on :9000** where Caddy's **layer4 (raw-TCP) plugin terminates TLS and
> forwards to the remote MinIO** at `10.0.0.2:9000` (the lab Synology, over the WireGuard
> tunnel `wg0`). The remote MinIO speaks plain HTTP; there is **no local `minio` container**
> here (it stays behind the `local-minio` profile, unused). Certs are **publicly-trusted
> Let's Encrypt**. Auth is **ORCID OAuth2 only** (LDAP not installed). The public host is
> `data.zhang-laboratory.org` (set via `DEPLOY_FQDN` in `.env`, but **also hardcoded in
> `caddy.json`** — Caddy JSON has no variable substitution).

### Topology

```
  browser ─HTTPS:443──▶ Caddy ── /lookup* ─▶ dserver:5000  (gunicorn, SCRIPT_NAME=/lookup)
  (public LE trust)       └──────  /  ──────▶ webapp:8080   (Vue dev server, hot-reload)
  browser ─HTTPS:9000─▶ Caddy[layer4]: TLS-terminate(LE) ─raw TCP─▶ 10.0.0.2:9000 (wg0)
  dserver ─HTTPS:9000─▶ (FQDN → caddy alias) ▶ Caddy[layer4] ─raw TCP─▶ 10.0.0.2:9000
```

Webapp (`/`) and API (`/lookup`) are **same-origin** ⇒ no CORS/mixed-content. S3 on :9000
is fronted by Caddy's **layer4** handler, NOT an HTTP reverse proxy (see "Why MinIO is NOT
fronted by an HTTP reverse proxy" in the shared base above). Externally published: Caddy
80/443/9000; everything else bound to `127.0.0.1`. dserver reaches S3 via a Docker network
**alias = `${DEPLOY_FQDN}` on the `caddy` service**, so it reads+signs against the same
`host:port` the browser uses (consistent SigV4 Host) and the public cert verifies normally.

### Prerequisites (external — cannot be tested from this box)

1. **Public DNS A record** `data.zhang-laboratory.org` → this host's public IP. Required for
   Let's Encrypt.
2. **Inbound :80** reachable from the internet for the ACME challenge (firewall opens
   80/443/9000). Validate against the LE **staging** CA first (flip the issuer `ca` in
   `caddy.json`) to avoid rate limits, then switch to production.
3. The **remote bucket `${S3_BUCKET}` must already exist** on the Synology MinIO (nothing in
   this stack creates it) and should be **private** (presigned URLs are load-bearing).
4. The remote MinIO's **CORS** must allow the webapp origin `https://${DEPLOY_FQDN}` for
   browser fetch/XHR of presigned URLs (a different origin: :443 → :9000). Set on the
   Synology (`MINIO_API_CORS_ALLOW_ORIGIN`); we can't inject it via layer4. Direct
   navigation to a presigned URL works regardless.

```bash
cp .env.template .env
# set DEPLOY_FQDN=data.zhang-laboratory.org, S3_BUCKET, S3_ACCESS_KEY_ID,
# S3_SECRET_ACCESS_KEY (remote MinIO creds), and optionally OAUTH2_CLIENT_ID/SECRET.
```
No cert-generation step: Caddy obtains/renews the LE cert itself (persisted in the
`caddy_data` volume) and shares it with the :9000 layer4 handler. **Keep `DEPLOY_FQDN` in
`.env` equal to the host hardcoded in `caddy.json`** (Caddy JSON has no `{$VAR}`).

### Files this site adds / changes (on top of the base)

| File | Role |
|---|---|
| `caddy.json` | Caddy **native JSON** config. `apps.http`: :80 ACME/redirect + :443 `/lookup*`→dserver, `/`→webapp. `apps.tls.certificates.automate`: LE cert for the FQDN. `apps.layer4`: :9000 → `tls` (terminate, same managed cert, ALPN pinned to `http/1.1`) → `proxy 10.0.0.2:9000`. **FQDN hardcoded** (no `{$VAR}` in JSON). |
| `compose/caddy/Dockerfile` | `xcaddy build --with github.com/mholt/caddy-l4` → custom Caddy image (`dserver_caddy_l4`) with the layer4 plugin. Build it **alone** (`docker compose build caddy`) — Go compile on a 2 GB box. |
| `docker-compose.override.yml` | `caddy` = the xcaddy image, `caddy.json` mounted, `caddy_data` volume, ports 80/443/9000, network alias `${DEPLOY_FQDN}`; `dserver` gunicorn+`SCRIPT_NAME`+`S3_ENDPOINT=https://${DEPLOY_FQDN}:9000`+OAuth2 URLs; `index-s3` S3_ENDPOINT; `webapp` env. No local minio, no `./certs`, no `AWS_CA_BUNDLE`, no LDAP. |
| `.env.template` | `DEPLOY_FQDN`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `OAUTH2_*`. |

### Why a layer4 proxy fronts :9000 (this site's solution)

See "Why MinIO is NOT fronted by an HTTP reverse proxy" in the shared base for the
header-canonicalization reason. Because S3 here is **remote and plain-HTTP**, we terminate
TLS with Caddy's **layer4 (`github.com/mholt/caddy-l4`) plugin**, which after the TLS
handshake forwards the connection as **raw TCP** — no HTTP parsing, so lowercase
`x-amz-meta-*` is preserved end to end. The same auto-managed LE cert serves :443 and the
:9000 layer4 handler via `apps.tls.certificates.automate` in `caddy.json` (the only config
form that reliably attaches a managed cert to the l4 handler). The l4 `tls` handler's ALPN
is pinned to `http/1.1` so it never negotiates h2 to the HTTP/1.1-only MinIO (browsers would
otherwise get an h2 framing error). Caddy reaches `10.0.0.2:9000` over the host's `wg0`
route, sharing the dserver container's bridge→wg0 egress (verify with
`docker compose exec caddy wget -qO- http://10.0.0.2:9000/minio/health/live`; fall back to
`network_mode: host` for caddy if it ever fails). **No `AWS_CA_BUNDLE`** — the cert is in
the public trust store.

### Certificates (publicly-trusted Let's Encrypt)

Caddy obtains and renews the cert automatically via **ACME** and persists it in the
`caddy_data` volume. No private CA, no client trust-store changes, no `/etc/hosts`. Needs
the public DNS record + inbound :80. Validate against the LE **staging** CA first
(switch the issuer `ca` in `caddy.json`), then flip to production and restart caddy.

### Data ingestion

The remote bucket must already exist (private). Push to the **HTTPS** endpoint
`https://${DEPLOY_FQDN}:9000` (from a host that trusts the public cert and resolves the
name). Index with `docker compose --profile index up index-s3` (runs
`flask base_uri index s3://${S3_BUCKET}` against the remote).

### Bring-up & verification

```bash
cp .env.template .env                          # set DEPLOY_FQDN, S3_BUCKET, S3 creds, ORCID
docker compose build caddy                     # xcaddy + caddy-l4 (Go build; run alone, ~2 GB box)
docker compose up -d                           # first run also builds venv + webapp; slow
docker compose ps                              # wait for healthy (dserver start_period 60s)

H=$(grep '^DEPLOY_FQDN=' .env | cut -d= -f2-)
docker compose exec caddy wget -qO- http://10.0.0.2:9000/minio/health/live   # 200 (caddy→wg0→remote)
curl --resolve $H:443:127.0.0.1 https://$H/lookup/config/health    # {"status":"healthy"}
curl --resolve $H:443:127.0.0.1 -I https://$H/                     # SPA 200, valid LE cert
curl --resolve $H:9000:127.0.0.1 https://$H:9000/minio/health/live # 200 via layer4 terminator
echo | openssl s_client -connect 127.0.0.1:9000 -servername $H 2>/dev/null \
  | openssl x509 -noout -issuer                                    # issuer = Let's Encrypt
# presigned URL: mint an admin JWT (flask user token admin, inside the container),
# GET /lookup/signed-urls/dataset/<url-enc-uri>, then fetch an item_url → 200 + file bytes
# (no SignatureDoesNotMatch, no metadata KeyError).
```

### Gotchas discovered during deployment (don't regress these)

- **Caddy must declare `networks: [dserver_net]`** — it's only in the override, so without
  it Compose drops it on the default network and it can't resolve `dserver`/`webapp`
  (symptom: 502, `lookup dserver … server misbehaving`).
- **`caddy.json` hardcodes the FQDN** and is **strict JSON** — Caddy native JSON has no
  `{$VAR}`/`{env.*}` substitution and **rejects unknown top-level fields** (e.g. a
  `_comment` key → `json: unknown field`). Keep the host in `caddy.json` equal to
  `DEPLOY_FQDN`.
- **layer4 `tls` ALPN must be `http/1.1`** — otherwise it negotiates h2 and raw-forwards h2
  frames to the HTTP/1.1-only MinIO; browsers then fail with an h2 framing error (botocore
  is unaffected as it only speaks HTTP/1.1).
- **The `dserver_image` bakes `/scripts/make-venv.sh`** — `dserver-build-venv` runs the
  image copy, not the bind-mounted `/app` one. After editing `make-venv.sh` (or advancing
  submodules it installs), `docker compose build dserver-build-venv` before rebuilding the
  venv, or the old script runs (symptom: wrong `setuptools`, missing plugins).
- **`setuptools<81`** (base `make-venv.sh`) — v81 removed `pkg_resources`, which `dtool-cli`
  imports unconditionally; without the pin the `dtool` CLI won't start.
- **No `AWS_CA_BUNDLE`** on this path — the S3 cert is publicly trusted. (Don't set the
  global `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` either.)

### Authentication on this site (ORCID OAuth2 only)

The mechanism is documented in **`## Authentication`** in the shared base; only the
site deltas:

- **ORCID only.** `VUE_APP_OAUTH2_ENABLED="true"`, `VUE_APP_SHOW_USERNAME_PASSWORD_FORM="false"`.
  The LDAP plugin is **not installed** (`INSTALL_LDAP_PLUGIN` unset) and the `ldap` service
  does not run, so there is no `/auth/ldap` token issuer.
- **Redirect URI to register at ORCID, exactly:** `https://${DEPLOY_FQDN}/lookup/auth/oauth2/callback`
  (set via `OAUTH2_REDIRECT_URI` in the override; the base `127.0.0.1:5000` default does not
  apply here). ORCID only redirects the user's browser, which trusts the LE chain — no CA
  import / `/etc/hosts`.
- **The username IS the ORCID iD.** New users hit `401` until the one-time provisioning
  (`flask user add` + `*_permission` on `s3://${S3_BUCKET}`, see the base). The `admin` DB
  user remains for CLI/scripted JWTs.
- LE-trusted ⇒ the server-side dserver→orcid.org token exchange and dserver→S3 reads both
  verify against the public trust store; no per-process CA bundle.

### Open items / things to confirm

- **Institutional SSO:** decide Path A (Entra OIDC) vs Path B (SAML) — see the shared
  "Future: institutional SSO" section; gated on an answer from institutional IT.
- **Inbound reachability:** confirm the firewall delivers `:443` and `:9000` from where
  clients connect (public vs VPN-only) — cannot be tested from the box itself.
- **RAM:** Vue dev server + mongo + postgres + gunicorn on ~2 GB is tight; the webapp `npm`
  compile is the OOM risk (`NODE_OPTIONS=--max-old-space-size=512` set).
