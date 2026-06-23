# Deployment model — shared base + per-site overlays

This branch (`https-deploy-base`) is the **neutral, site-agnostic** HTTPS-deployment
recipe. It is **not deployed directly**. Concrete deployments are *site branches* that
build on this base and add only their site-specific pieces.

```
https-deploy-base            (this branch — shared, never deployed directly)
├── acme-deployment          = base + its override + Caddyfile        + .env (demo)
└── zhanglab-data            = base + its override + caddy.json (+xcaddy Dockerfile) + .env (lab)
```

Both site branches diverged from the same ancestor (`752bdcf`) and made *contradictory*
choices on two axes (how `:9000`/MinIO is fronted, and which auth method is used), so
neither is a prefix of the other. This base captures what they genuinely share; each site
overlays the rest.

## The seam

`docker compose` auto-merges `docker-compose.override.yml` on top of `docker-compose.yml`.
That is the boundary: **base ships `docker-compose.yml` (+ shared scripts); each site ships
its own `docker-compose.override.yml` + Caddy config + `.env`.** Base intentionally ships
**no** `docker-compose.override.yml` and **no** `caddy` service.

| Lives in **base** (this branch) | Lives in **each site** (its overlay) |
|---|---|
| All service definitions, `127.0.0.1` binds, direct-mongo plugin | The MinIO-fronting mechanism: cert-sync sidecar + MinIO native TLS *(acme)* vs Caddy **layer4** raw-TCP to a remote MinIO *(zhanglab)* |
| `compose/dserver/scripts/start-dserver-gunicorn.sh` (gunicorn, `SCRIPT_NAME=/lookup`) | The `caddy` service itself (plain `caddy:2-alpine`+`Caddyfile` vs xcaddy image + `caddy.json`) |
| `compose/dserver/scripts/export-s3-env.sh` (assembles the hyphenated `DTOOL_S3_*_<bucket>` trio at runtime) | Which optional services run, via `profiles` (`local-minio`, `ldap`) |
| `compose/dserver/scripts/make-venv.sh` (common plugin install set) | Bucket / credentials / FQDN / ACME email — all via `.env` |
| `docker-compose.yml`: services parameterized by `${S3_BUCKET}` + `S3_*`; `minio`/`minio-init`/`ldap` behind profiles | Auth method via env toggles (`VUE_APP_OAUTH2_ENABLED`, `VUE_APP_SHOW_USERNAME_PASSWORD_FORM`, LDAP_* …) |

## Why base is parameterized (and acme will be refactored onto it)

`zhanglab-data`'s `docker-compose.yml` was already neutral — S3 backend driven by
`${S3_BUCKET}` / `S3_*`, and `minio`/`minio-init`/`ldap` gated behind `profiles`. That
parameterized file *is* this base. `acme-deployment` still hardcodes its demo choices
(`dtool-bucket`, `minioadmin`, LDAP always on) in its `docker-compose.yml`; refactoring it
onto this base (de-hardcoding the bucket/creds, enabling LDAP via env/profile) is a
**separate follow-up step**.

## Composing a site

```bash
# in a site branch (override + caddy config + .env present):
docker compose up -d            # = docker-compose.yml (base) + docker-compose.override.yml (site)
```

The base alone is not meant to `up` (it has no TLS/caddy layer and requires `${S3_BUCKET}`).

## Follow-ups (not done in this base draft)

- **`acme-deployment` refactor** onto this base: move its hardcoded bucket/creds to `.env`,
  and gate the LDAP plugin install in `make-venv.sh` behind an env flag
  (e.g. `INSTALL_LDAP_PLUGIN`, default `false`) so the *same* script serves both an
  ORCID-only site and an LDAP site. (Base currently leaves the LDAP install commented out =
  ORCID-only default, matching `zhanglab-data`.)
- **Doc split**: move the site-specific recipe sections out of `CLAUDE.md` into the site
  branches, leaving the shared recipe here. (`CLAUDE.md` and `.env.template` are untouched
  in this draft.)
- **Re-express the site branches as `base + overlay`** (rebase each onto this base carrying
  only their site files) once the structure is reviewed.
