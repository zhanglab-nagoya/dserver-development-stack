# CLAUDE.md — dserver-development-stack

Guidance for Claude Code working in this repository. This is a **Docker Compose
development stack** that wires together `dserver` (a Flask REST API for dtool dataset
metadata) and the `dtool-lookup-webapp` Vue.js frontend, plus all their backing services
and plugins, from local source checkouts (git submodules) installed in editable mode.

> There is also a `README.md` aimed at end users. It is partly **out of date** — see
> "Known README discrepancies" at the bottom before trusting it. This file reflects what
> the code actually does.

> **Branch note:** the **`zhanglab-data`** branch adds an HTTPS deployment layer on top
> of the base dev stack (Caddy TLS proxy, gunicorn, MinIO over TLS). The deployment is
> parameterised by a single environment variable (`DEPLOY_FQDN`) so the config files
> here name no specific host. See **"HTTPS deployment recipe (this branch)"** below.
> The sections after it describe the plain dev stack (`main`), which still applies
> underneath.

## HTTPS deployment recipe (this branch)

Serves the **webapp on `https://${DEPLOY_FQDN}/`**, the **dserver API under `/lookup`**
(both on :443 via Caddy), and **S3/MinIO over its own TLS on :9000** for browser-usable
presigned URLs. One local CA signs the single cert used by both Caddy and MinIO. Layered
on the base stack via `docker-compose.override.yml` (auto-merged) plus a few base edits.
The host name is supplied via `DEPLOY_FQDN` in `.env`; none of the config files name a
specific host.

### Topology

```
  browser ─HTTPS:443──▶ Caddy ── /lookup* ─▶ dserver:5000  (gunicorn, SCRIPT_NAME=/lookup)
  (trusts ca.crt)         └──────  /  ──────▶ webapp:8080   (Vue dev server, hot-reload)
  browser ─HTTPS:9000─────────────────────▶ minio:9000     (MinIO native TLS; presign host)
  dserver ─HTTPS:9000─▶ (FQDN → minio alias) ▶ minio:9000   (read + sign, no proxy)
```

Webapp (`/`) and API (`/lookup`) are **same-origin** ⇒ no CORS, no mixed-content. MinIO is
**not** proxied by Caddy (see "Why MinIO does its own TLS"). Externally published: Caddy
80/443 and MinIO 9000; everything else is bound to `127.0.0.1`.

### Prerequisite: set DEPLOY_FQDN and generate the certs first

```bash
cp .env.template .env
# edit .env and set DEPLOY_FQDN=<your-host>  (and optionally OAUTH2_CLIENT_ID/SECRET)
./gen-tls-certs.sh        # writes ./certs/{ca,server}.{crt,key} (git-ignored)
```
`gen-tls-certs.sh` reads `DEPLOY_FQDN` from `.env` (or the shell) and fails loudly if it
is unset. One local CA (`ca.crt`/`ca.key`) signs one SAN leaf (`server.crt`/`server.key`,
SAN = `$DEPLOY_FQDN`,`minio`,`localhost`,`127.0.0.1`). Caddy serves it on :443 and MinIO
on :9000. Must exist before `docker compose up` (bind-mounted into both).

### Files this deployment adds / changes

| File | Role |
|---|---|
| `.env.template` | Documents `DEPLOY_FQDN` (and `OAUTH2_*`); copy to `.env`. |
| `gen-tls-certs.sh` | Generates the local CA + shared server cert into `./certs` (git-ignored). Reads `DEPLOY_FQDN`. |
| `Caddyfile` | TLS (`tls /certs/server.crt …`) + routing only: `/lookup*`→dserver, `/`→webapp. Site address is `{$DEPLOY_FQDN}`. Does **not** proxy S3. |
| `docker-compose.override.yml` | Adds `caddy` (on `dserver_net`!); MinIO native TLS (`--certs-dir`, :9000, FQDN alias); `minio-init` over TLS; `dserver` gunicorn+`SCRIPT_NAME`+S3/CA/OAuth2 env; `index-s3` + `webapp` env. All host-specific values come from `${DEPLOY_FQDN}`. |
| `compose/dserver/scripts/start-dserver-gunicorn.sh` | Same prep as `start-dserver.sh`, then `exec gunicorn "dservercore:create_app()"`. Bind-mounted via `/app` (no image rebuild). |
| `compose/dserver/scripts/make-venv.sh` (edit) | Pin `setuptools<81` (keeps `pkg_resources` for dtool-cli); add `dtool-create`/`dtool-symlink`/`dtool-http`/`ruamel.yaml` (create/freeze/cp). |
| `compose/webapp/vue.config.js` | Bind-mounted over the container's; `devServer.allowedHosts:"all"` for the proxied FQDN. Avoids editing the submodule. |
| `docker-compose.yml` (base edits) | postgres/mongo/minio-console/dserver/webapp bound to `127.0.0.1` (MinIO :9000 is re-published by the override). |

### Why gunicorn + `SCRIPT_NAME=/lookup`

Single `/lookup` prefix (modelled on `dserver-minimal`'s single-container) ⇒ the proxy
needs two rules, not an enumeration of dservercore's ~13 blueprints. Gunicorn applies
`SCRIPT_NAME=/lookup` to the WSGI environ: `/lookup/config/health` splits into
`SCRIPT_NAME=/lookup` + `PATH_INFO=/config/health`, so routing matches and
`url_for(_external=True)` emits correct `https://…/lookup/…`. `flask run` (Werkzeug) does
**not** honour `SCRIPT_NAME` the same way. Caddy uses `handle /lookup*` (not `handle_path`)
to keep the prefix; the healthcheck probes `/lookup/config/health`.

### Why MinIO does its own TLS (not behind Caddy)

Caddy (Go `net/http`) **canonicalises response header names** — MinIO's lowercase
`x-amz-meta-type` becomes `X-Amz-Meta-Type`. botocore slices the metadata key *after* the
`x-amz-meta-` prefix **without lowercasing**, so proxied reads come back keyed `Type`/
`Handle` and dtool-s3's lowercase lookups `KeyError` (`'type'`). The body is intact, so
browser downloads through a proxy are fine, but dserver's **server-side reads** (needed to
mint presigned URLs) break. Fix: MinIO terminates its own TLS on :9000 (lowercase headers
preserved); Caddy is out of the S3 path entirely.

Note the signed-url plugin's `SIGNED_URL_HOST_REWRITE` is a **post-signing string
replace** (`__init__.py:222`) and breaks SigV4 (which signs the Host) — leave it unset.
We instead sign for the real public host:

- `dserver`/`index-s3` use `DTOOL_S3_ENDPOINT_dtool-bucket=https://${DEPLOY_FQDN}:9000`.
  The `minio` service has a **network alias = `${DEPLOY_FQDN}`**, so that name resolves
  to MinIO inside the network too — dserver reads **and** signs against the same
  host:port the browser uses (consistent SigV4 Host). Trust is scoped to boto via
  **`AWS_CA_BUNDLE=/certs/ca.crt` only** — do *not* set `REQUESTS_CA_BUNDLE`/
  `SSL_CERT_FILE` globally, or public HTTPS (ORCID token exchange, pip) would fail to
  verify against the private root.
- Path-style addressing throughout (`…:9000/dtool-bucket/<key>`); MinIO has no base-path
  mode, so a `/s3/…` subpath on :443 is not viable. MinIO CORS is `*` (base compose).

**Caveat:** the dev bucket is **public-read** (`mc anonymous set public`), so presigned
URLs add little protection until it's made private.

### Certificate trust (shared local CA, not publicly trusted)

The recipe assumes no public DNS record for `$DEPLOY_FQDN` (so Let's Encrypt is not
usable). HTTPS is "valid" only for clients that trust `./certs/ca.crt`. On each client:
```bash
# copy ./certs/ca.crt off the host, then (Linux):
sudo cp ca.crt /usr/local/share/ca-certificates/local-ca.crt && sudo update-ca-certificates
# macOS: add to login keychain as "Always Trust"; Firefox/Chrome: import in cert settings.
# And resolve the name (no public DNS) — client /etc/hosts (or the VPN):
echo "<PUBLIC_IP> <your-host>" | sudo tee -a /etc/hosts
```
To go publicly-trusted later: have your network admin add an A record for `$DEPLOY_FQDN`
and open inbound :80, then point Caddy at a Let's Encrypt cert (and reissue MinIO's cert
from the same trusted chain, or front MinIO with a trusted cert).

### Data ingestion

MinIO is TLS-only now, so push to the **HTTPS** endpoint (no plaintext `http://minio:9000`).
From inside the dserver container the bundled client works:
```bash
docker compose exec dserver bash -c "source /venv/bin/activate && bash /scripts/create-test-dataset.sh"
```
Then index: `docker compose --profile index up index-s3` (or `flask base_uri index s3://dtool-bucket`).
Host-side clients set `DTOOL_S3_ENDPOINT_dtool-bucket=https://$DEPLOY_FQDN:9000` and
trust `ca.crt` (e.g. `AWS_CA_BUNDLE`/`REQUESTS_CA_BUNDLE`).

### Bring-up & verification

```bash
cp .env.template .env                          # set DEPLOY_FQDN (+ optional ORCID creds)
./gen-tls-certs.sh                             # REQUIRED first — creates ./certs
docker compose up -d --build                   # first run builds venv + webapp; slow on ~2 GB RAM
docker compose ps                              # wait for healthy (dserver start_period 60s)

CA=./certs/ca.crt
H=$(grep '^DEPLOY_FQDN=' .env | cut -d= -f2-)
curl --cacert $CA --resolve $H:443:127.0.0.1 https://$H/lookup/config/health   # {"status":"healthy"}
curl --cacert $CA --resolve $H:443:127.0.0.1 -I https://$H/                     # SPA 200
curl --cacert $CA --resolve $H:9000:127.0.0.1 https://$H:9000/minio/health/live # 200 (MinIO TLS)
# presigned URL: mint an admin JWT (see indexall.sh), GET /lookup/signed-urls/dataset/<url-enc-uri>,
# then fetch an item_url with --resolve $H:9000:127.0.0.1 → 200 + file bytes.
```

### Gotchas discovered during deployment (don't regress these)

- **Caddy must declare `networks: [dserver_net]`** — it's only in the override, so without
  it Compose drops it on the default network and it can't resolve `dserver`/`webapp`
  (symptom: 502, `lookup dserver … server misbehaving`).
- **Caddy needs `DEPLOY_FQDN` in its process env** — the Caddyfile site address is
  `{$DEPLOY_FQDN}`, which is substituted at parse time. The override passes it through
  via `environment:`. Without it, Caddy refuses to start.
- **`setuptools<81`** — v81 removed `pkg_resources`, which `dtool-cli` imports
  unconditionally; without the pin the `dtool` CLI won't start.
- **dtool create/freeze/cp** need `dtool-create` (+`dtool-symlink`,`dtool-http`,
  `ruamel.yaml`); `dtool-cli`+`dtool-info` alone don't provide them. There is no
  `dtool-cp` package — `cp`/`copy` live in `dtool-create`.
- **`AWS_CA_BUNDLE` only** for the internal CA (see above) — not the global requests/ssl
  bundles.

### Authentication (ORCID OAuth2 — active, verified)

Real ORCID login is wired and working. Flow: webapp → `GET /lookup/auth/login` → ORCID →
`GET /lookup/auth/callback` → dserver mints an RS256 JWT → webapp (token in the redirect).

- **Credentials:** `OAUTH2_CLIENT_ID`/`OAUTH2_CLIENT_SECRET` live in `.env` (git-ignored).
  Register an app at orcid.org (or sandbox.orcid.org) for the Public API.
- **Redirect URI to register at ORCID, exactly:**
  `https://$DEPLOY_FQDN/lookup/auth/callback`
  (derived as `OAUTH2_BASE_URL` + `/auth/callback`; mismatch ⇒ ORCID rejects the request).
  ORCID never fetches it — only the user's browser does — so a private CA / `/etc/hosts`
  / VPN setup is fine as long as the browser trusts `ca.crt` and resolves the FQDN.
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
- The internal CA is scoped to boto via `AWS_CA_BUNDLE` only, so the server-side
  dserver→orcid.org token exchange verifies against the public trust store (don't set
  `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` globally).
- A dev-only alternative that accepts any username/password (`dserver-dummy-token-generator`,
  livMatS/dserver-development-stack PR #2) exists but is **not** used here — it is
  unauthenticated, so only acceptable behind a VPN/internal firewall.
- **Webapp-side toggle:** `VUE_APP_AUTH_ENABLED` (default `"true"` in
  `docker-compose.yml`). Setting it to `"false"` hides the SignIn screen and lets
  the webapp call the API without an `Authorization` header. This is a frontend
  switch only — it **must** be paired with dserver running in its own no-auth mode,
  otherwise every request returns 401. The webapp's `/users/<username>/summary`
  call was also moved to `/me/summary` so the panel works in both modes without
  needing a username from a JWT.

### Future: institutional SSO (exploration, not yet implemented)

Goal: let users authenticate with institutional credentials instead of (or alongside)
ORCID. The available plugin is **OIDC/OAuth2-only**; SAML needs the separate SAML plugin
in this repo. Two viable paths, depending on what your IdP speaks:

- **Path A — OIDC via Microsoft Entra ID (easiest, config-only).** If your institution's
  identity provider includes a Microsoft 365 / Entra ID tenant and IT will let you
  register an app, configure the existing OAuth2 plugin like ORCID/Google:
  ```
  OAUTH2_AUTHORIZATION_URL = https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/authorize
  OAUTH2_TOKEN_URL         = https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token
  OAUTH2_USERINFO_URL      = https://graph.microsoft.com/oidc/userinfo
  OAUTH2_SCOPE             = openid email profile
  # register redirect URI: https://$DEPLOY_FQDN/lookup/auth/callback
  ```
  Tolerant of a no-public-DNS setup (Entra doesn't fetch the redirect URI; the browser
  does). Nuance: the username (UPN) is usually in the **id_token**, which the plugin
  doesn't decode — it reads the token response + `/oidc/userinfo`. Map username to
  `email`/`sub`, or add a few lines to read `preferred_username` from the id_token.

- **Path B — SAML via a Shibboleth / academic federation IdP.** Needed for standard
  attribute release (`eduPersonPrincipalName`, `mail`, affiliation) through federations
  such as **GakuNin** (Japan, NII), **eduGAIN** (international), or InCommon (US). The
  OAuth2 plugin can't do SAML; two ways to add it:
  - **Native SAML SP plugin (chosen direction; drafted).** `dserver-token-generator-plugin-saml/`
    is a sibling `dservercore.extension` (pysaml2) that makes dserver a SAML SP directly —
    `/login` (AuthnRequest), `/acs`, `/metadata`, `/sls` — and mints the same dserver JWT.
    Prefix is configurable (`SAML_URL_PREFIX`, default `/saml` to coexist with OAuth2's
    `/auth`). Pure logic (attribute map, JWT) is unit-tested; the live flow is untested
    pending IdP metadata + SP registration. **Not yet wired into the stack** (needs
    `xmlsec1` in the Dockerfile + install in `make-venv.sh`) — see its `README.md`.
  - **Proxy alternative:** run **SATOSA** (SAML2 SP ↔ OIDC OP) and point the existing
    OAuth2 plugin at it — no dserver code, but an extra container.
  - **Prerequisites (either way):** register dserver as an SP with the federation
    operator + your institutional IdP admin (metadata exchange + attribute release) and
    **publicly reachable SP endpoints** — conflicts with the current no-public-DNS /
    private-CA setup, so resolve that first.

**Gating step:** ask your institutional IT whether a self-hosted service may register an
**Entra ID OIDC app** (→ Path A) or must integrate as a **SAML SP** in your federation
(→ Path B). The provisioning model is unchanged from ORCID: the IdP-supplied identifier
(Entra UPN / SAML ePPN) becomes the dserver username and needs a one-time
`flask user add` to gain permissions.

Refs: GakuNin <https://www.gakunin.jp/en>; SATOSA
<https://github.com/IdentityPython/SATOSA> (saml2-to-oidc).

### Open items / things to confirm

- **Institutional SSO:** decide Path A (Entra OIDC) vs Path B (SAML via SATOSA or the
  native plugin) — gated on an answer from institutional IT about Entra app registration
  vs SAML SP onboarding.
- **Inbound reachability:** confirm the firewall delivers `:443` and `:9000` from where
  clients connect (public vs VPN-only) — cannot be tested from the box itself.
- **RAM:** Vue dev server + mongo + postgres + minio + gunicorn on ~2 GB is tight; the
  webapp `npm` compile is the OOM risk (`NODE_OPTIONS=--max-old-space-size=512` set).

### Submodules over HTTPS on hosts with no GitHub SSH key

`.gitmodules` uses `git@github.com:` SSH URLs. If the host has no GitHub SSH key, all
submodules are public, so init them over HTTPS without modifying `.gitmodules`:
```bash
git -c url."https://github.com/".insteadOf="git@github.com:" submodule update --init --recursive
```

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
The 15 submodules are **not checked out** in a fresh clone (the directories are empty
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
  `dserver-dependency-graph-plugin`, `dserver-direct-mongo-plugin`,
  `dserver-signed-url-plugin`, `dserver-token-generator-plugin-oauth2`,
  `dserver-token-generator-plugin-ldap`; from PyPI: `dtool-cli`, `dtool-info`,
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

## Authentication

Two token generators run side by side as `dservercore.extension` plugins (dservercore
registers every extension blueprint, so multiple coexist as long as their URL prefixes
differ). Both mint RS256 JWTs signed with the same key dserver verifies; both gate access
on dserver's own user table (`sub` claim must be a provisioned user, else 401 on every
route). The webapp shows the **ORCID button and the username/password form together**.

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

The restored simple login. The webapp's username/password form POSTs `{username,password}`
to `POST /auth/ldap/token` (`VUE_APP_DTOOL_LOOKUP_SERVER_TOKEN_GENERATOR_URL`); the plugin
binds against LDAP, and on success mints a JWT.

- **Bundled dev directory:** the `ldap` service (osixia/openldap, seeded via
  `compose/ldap/bootstrap/*.ldif`) is seeded with
  **`testuser` / `test_password`**. Point `LDAP_URI` (+ `LDAP_BIND_DN`, `LDAP_USER_BASE_DN`,
  `LDAP_USER_FILTER`, …) at an external/corporate LDAP for real use; add users there, not in
  dserver. LDAP config lives in the `dserver` service env in `docker-compose.yml`; see the
  plugin's `README.md` for all knobs (search-then-bind vs `LDAP_USER_DN_TEMPLATE`, TLS, etc.).
- **Auto-provisioning:** with `LDAP_AUTO_PROVISION_USERS=true`, a first successful LDAP login
  creates the dserver user and grants search/register on `LDAP_DEFAULT_BASE_URIS`
  (`s3://dtool-bucket`) — so LDAP users work with zero manual steps. Set it to `false` to
  require an admin to `flask user add` them instead.

### User provisioning (both methods) & toggles

```
docker compose exec dserver bash -lc 'source /venv/bin/activate && \
  flask user add <username>            # add --is_admin for administrators
  flask user search_permission <username> s3://dtool-bucket
  flask user register_permission <username> s3://dtool-bucket'
```
Provisioned users persist in Postgres. The `admin` DB user remains for CLI/scripted JWTs
(see `indexall.sh`).

- **Webapp-side toggle:** `VUE_APP_AUTH_ENABLED` (default `"true"`). Setting it to `"false"`
  hides the SignIn screen and lets the webapp call the API without an `Authorization` header
  — a frontend switch only; **must** be paired with dserver in its own no-auth mode or every
  request returns 401. The webapp's `/users/<username>/summary` call was moved to
  `/me/summary` so the panel works in both modes.
- `VUE_APP_SHOW_USERNAME_PASSWORD_FORM` (now `"true"`) shows the form; `VUE_APP_OAUTH2_ENABLED`
  shows the ORCID button. Either or both can be enabled.
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

## Submodules (15)
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
