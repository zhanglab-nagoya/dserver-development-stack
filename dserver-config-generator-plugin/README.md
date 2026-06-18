# dserver-config-generator-plugin

A [dserver](https://github.com/jic-dtool/dservercore) extension that **dynamically
generates per-user** `dtool.json` and `dtool_readme.yml` on authenticated routes,
replacing static download templates.

## Routes (prefix `/config-generator`, JWT-protected)

- `GET /config-generator/dtool.json` → personalized dtool config (attachment)
- `GET /config-generator/dtool_readme.yml` → personalized readme template (attachment)
- `GET /config-generator/info` → non-secret diagnostics

The caller is identified from the JWT (`sub`); `username`, `display_name` and the
dataset prefix `u/<username>/` are filled in from dserver's own user record.

## Credential providers (MinIO is optional)

The S3 credentials embedded in `dtool.json` come from a pluggable provider selected
by `CONFIG_GENERATOR_CREDENTIAL_PROVIDER`:

| Provider | Behaviour | Extra deps |
|---|---|---|
| `none` (default) | Emit endpoint + prefix, **no secret** (user brings their own keys) | none |
| `static` | Emit operator-configured shared key/secret | none |
| `minio` | Mint a per-user MinIO **service account** scoped to `u/<username>/` | `minio` (`[minio]` extra) |

**The plugin runs without MinIO.** MinIO support lives entirely in
`credentials/minio.py` (lazy `import minio`) and the `[minio]` extra; remove both to
strip it — nothing else references MinIO.

## Configuration (environment)

Core: `CONFIG_GENERATOR_CREDENTIAL_PROVIDER`, `CONFIG_GENERATOR_S3_PUBLIC_ENDPOINT`,
`CONFIG_GENERATOR_S3_BUCKET`, `CONFIG_GENERATOR_DATASET_PREFIX_TEMPLATE`,
`CONFIG_GENERATOR_DSERVER_URL`, `CONFIG_GENERATOR_TOKEN_GENERATOR_URL`,
`CONFIG_GENERATOR_DEFAULT_BASE_URI`, `CONFIG_GENERATOR_DTOOL_JSON_TEMPLATE` /
`CONFIG_GENERATOR_README_TEMPLATE` (override the built-in templates).

`static`: `CONFIG_GENERATOR_STATIC_ACCESS_KEY` / `_SECRET_KEY`.
`minio`: `CONFIG_GENERATOR_MINIO_ADMIN_ENDPOINT`, `_MINIO_ADMIN_ACCESS_KEY`,
`_MINIO_ADMIN_SECRET_KEY`, `_MINIO_SECURE`, `_MINIO_SVCACCT_EXPIRY_SECONDS`,
`_MINIO_POLICY_TEMPLATE`.

## Security

`minio` provider: each download mints a fresh, prefix-scoped service account; downloaded
credentials are time-limited if `_MINIO_SVCACCT_EXPIRY_SECONDS` is set. Verify the inline
policy denies access outside `u/<username>/`. Dev defaults embed admin creds — never for
production as-is.
