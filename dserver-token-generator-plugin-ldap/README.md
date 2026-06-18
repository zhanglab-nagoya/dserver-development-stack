# dserver-token-generator-plugin-ldap

A simple **username/password** token generator plugin for
[dserver](https://github.com/jic-dtool/dservercore). It authenticates
credentials against an **LDAP** directory and issues RS256 JWTs that dserver
verifies with its existing public key.

It is a `dservercore.extension` plugin modeled on
`dserver-token-generator-plugin-oauth2`, and is designed to run **alongside**
that plugin: this one owns the `/auth/ldap` prefix, OAuth2 owns `/auth/oauth2`.
A user can therefore log in with either ORCID (OAuth2) or username/password
(LDAP) against the same dserver.

## Endpoint

`POST /auth/ldap/token` — body `{"username": ..., "password": ...}` →
`{"token": "<jwt>", "username": ..., "token_type": "Bearer"}` (401 on bad
credentials). This matches the dtool-lookup-webapp username/password form.

## Configuration (environment variables)

| Variable | Purpose | Example |
|---|---|---|
| `LDAP_URI` | Directory URL | `ldap://ldap:1389` |
| `LDAP_USE_SSL` / `LDAP_START_TLS` | LDAPS / StartTLS | `false` |
| `LDAP_BIND_DN` / `LDAP_BIND_PASSWORD` | Service account for search-then-bind (empty = anonymous) | `cn=admin,dc=example,dc=org` |
| `LDAP_USER_BASE_DN` | Search base | `ou=users,dc=example,dc=org` |
| `LDAP_USER_FILTER` | Search filter; `{username}` substituted (escaped) | `(cn={username})` |
| `LDAP_USER_DN_TEMPLATE` | Direct-bind DN template (skips search if set) | `cn={username},ou=users,dc=example,dc=org` |
| `LDAP_ATTRIBUTE_MAP` | `ldapAttr:internal` pairs | `mail:email,cn:display_name` |
| `LDAP_AUTO_PROVISION_USERS` | Create the user in dserver on first login | `true` |
| `LDAP_DEFAULT_BASE_URIS` | Base URIs to grant on provision (comma-sep) | `s3://dtool-bucket` |
| `LDAP_GRANT_REGISTER` | Also grant register (not just search) | `true` |
| `JWT_PRIVATE_KEY_FILE` / `JWT_PUBLIC_KEY_FILE` / `JWT_ALGORITHM` | Shared JWT signing config | (same as dserver) |

## Auth vs. authorization

LDAP proves **who** the user is. dserver's own user table decides **what** they
may access. With `LDAP_AUTO_PROVISION_USERS=true` the plugin creates the user
in dserver on first successful login and grants search/register on
`LDAP_DEFAULT_BASE_URIS`; otherwise an admin must `flask user add` them.

## Security

Dev defaults use plaintext LDAP and skip TLS certificate validation. Configure
LDAPS/StartTLS with proper certificate validation for anything exposed.
