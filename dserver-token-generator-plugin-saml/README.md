# dserver-token-generator-plugin-saml

Native **SAML 2.0** token generator for dserver — a `dservercore.extension` sibling to
`dserver-token-generator-plugin-oauth2`. It makes dserver a SAML **Service Provider (SP)**,
authenticates users against a SAML 2.0 IdP (e.g. an institutional Shibboleth IdP, or a
federation IdP such as one of the **GakuNin** academic federation members in Japan),
and mints a dserver-compatible RS256 JWT — so dserver validates it like a token from any
other generator and the webapp/`/lookup` wiring is unchanged.

> **Status: draft / not yet wired into the running stack.** The pure logic (attribute
> mapping, JWT minting) is unit-tested; the live SAML round-trip is untested pending IdP
> metadata + SP registration. Activating it requires the steps below.

## Routes (under the configurable prefix, default `/auth/saml`)

| Route | Purpose |
|---|---|
| `GET /login` | Build a SAML `AuthnRequest` and redirect to the IdP |
| `POST /acs` | Assertion Consumer Service — validate the signed Response, map attributes → username, mint a JWT, redirect to the frontend with `?token=` |
| `GET /metadata` | This SP's SAML metadata XML (register with NII/GakuNin) |
| `GET /sls` | Single Logout (best-effort local clear for now) |
| `GET /info` | Provider info for the webapp login screen |

## Configuration (environment)

| Var | Default | Notes |
|---|---|---|
| `SAML_URL_PREFIX` | `/auth/saml` | **Configurable mount point**, in parallel with the sibling plugins `/auth/oauth2` and `/auth/ldap`. |
| `SAML_BASE_URL` | `http://localhost:5000` | Public base incl. any `SCRIPT_NAME` (e.g. `https://<your-host>/lookup`) |
| `SAML_SP_ENTITY_ID` | `<BASE_URL><PREFIX>/metadata` | SP entityID |
| `SAML_IDP_METADATA_URL` / `SAML_IDP_METADATA_FILE` | — | IdP / federation metadata source |
| `SAML_IDP_ENTITY_ID` | — | Pin one IdP when the metadata holds many (e.g. all of GakuNin) |
| `SAML_SP_KEY_FILE` / `SAML_SP_CERT_FILE` | — | SP signing/encryption keypair (PEM) |
| `SAML_ATTRIBUTE_MAP` | `eduPersonPrincipalName:user_id,mail:email,displayName:display_name` | SAML attr → internal field |
| `SAML_USERNAME_FIELD` | `user_id` | which internal field becomes the dserver username (ePPN for GakuNin) |
| `SAML_AUTHN_REQUESTS_SIGNED` / `SAML_WANT_RESPONSE_SIGNED` / `SAML_WANT_ASSERTIONS_SIGNED` | `true` | |
| `SAML_LOGIN_SUCCESS_REDIRECT` / `SAML_LOGIN_ERROR_REDIRECT` | derived from `SAML_BASE_URL` | webapp redirects |
| `SAML_XMLSEC_BINARY` | `/usr/bin/xmlsec1` | path to xmlsec1 |
| `JWT_PRIVATE_KEY_FILE` / `JWT_ALGORITHM` | (shared with dserver) | token signing |

## Activating it (not done automatically — keeps the running stack intact)

1. **System deps** (pysaml2 needs xmlsec) — add to `compose/dserver/Dockerfile`:
   ```dockerfile
   RUN apt-get update && apt-get install --yes --no-install-recommends \
       xmlsec1 libxmlsec1-dev libxml2-dev pkg-config && rm -rf /var/lib/apt/lists/*
   ```
2. **Install the plugin** in `compose/dserver/scripts/make-venv.sh` (and rebuild the venv):
   ```sh
   pip install -e /app/dserver-token-generator-plugin-saml
   ```
   It registers as a `dservercore.extension`. The default `SAML_URL_PREFIX=/auth/saml` sits
   alongside `/auth/oauth2` (OAuth2) and `/auth/ldap` (LDAP) without collision.
3. **SP keypair**: generate a signing/encryption cert+key for the SP and point
   `SAML_SP_KEY_FILE`/`SAML_SP_CERT_FILE` at them.
4. **IdP metadata**: set `SAML_IDP_METADATA_URL` (federation metadata feed or a specific
   institutional IdP) and, if needed, pin `SAML_IDP_ENTITY_ID`.
5. **Register the SP** (the institutional step): publish `<BASE_URL><PREFIX>/metadata` to
   the federation operator and/or the institutional IdP admin, and **request attribute
   release** (at least `eduPersonPrincipalName`). This requires publicly reachable SP
   endpoints.
6. Set `SAML_BASE_URL=https://<your-host>/lookup` and point the webapp's login at
   `…/auth/saml/login`.

## Provisioning

The IdP-supplied identifier (ePPN) becomes the dserver username; a new user authenticates
but gets `401` until provisioned: `flask user add <ePPN>` (+ `search_permission`). Same
model as the OAuth2/ORCID plugin.

## Multi-IdP / discovery

`SAML_IDP_ENTITY_ID` pins a single IdP. For a federation with many IdPs (full GakuNin), a
discovery service (DS/WAYF) would be the next addition; not implemented in this draft.
