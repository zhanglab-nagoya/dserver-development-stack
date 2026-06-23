"""
Configuration management for the LDAP token generator.

Loads LDAP connection / search settings and the (shared) JWT signing config
from environment variables. JwtConfig mirrors the OAuth2 plugin so both
generators produce dserver-compatible tokens signed with the same key.
"""

import os
from dataclasses import dataclass, field


@dataclass
class LdapProviderConfig:
    """LDAP directory connection and user-lookup configuration."""

    # Connection
    uri: str = ""                       # e.g. ldap://ldap:1389 or ldaps://host:636
    use_ssl: bool = False               # LDAPS
    start_tls: bool = False             # StartTLS on a plain connection

    # Service account used to search for the user entry (search-then-bind).
    # Leave empty to attempt an anonymous search bind.
    bind_dn: str = ""
    bind_password: str = ""

    # Search-then-bind parameters
    user_base_dn: str = ""              # e.g. ou=users,dc=example,dc=org
    user_filter: str = "(uid={username})"  # {username} is substituted (escaped)

    # Alternative: direct-bind template (skips the search). When set, takes
    # precedence over search-then-bind, e.g. "cn={username},ou=users,dc=example,dc=org"
    user_dn_template: str = ""

    # LDAP attribute -> internal field mapping (e.g. "mail:email,cn:display_name")
    attribute_map: dict = field(default_factory=lambda: {
        "mail": "email",
        "cn": "display_name",
    })

    @classmethod
    def from_env(cls) -> "LdapProviderConfig":
        """Create configuration from environment variables."""
        attribute_map_str = os.environ.get("LDAP_ATTRIBUTE_MAP", "")
        if attribute_map_str:
            attribute_map = {}
            for mapping in attribute_map_str.split(","):
                if ":" in mapping:
                    key, value = mapping.split(":", 1)
                    attribute_map[key.strip()] = value.strip()
        else:
            attribute_map = {"mail": "email", "cn": "display_name"}

        def _bool(name: str, default: str = "false") -> bool:
            return os.environ.get(name, default).lower() == "true"

        return cls(
            uri=os.environ.get("LDAP_URI", ""),
            use_ssl=_bool("LDAP_USE_SSL"),
            start_tls=_bool("LDAP_START_TLS"),
            bind_dn=os.environ.get("LDAP_BIND_DN", ""),
            bind_password=os.environ.get("LDAP_BIND_PASSWORD", ""),
            user_base_dn=os.environ.get("LDAP_USER_BASE_DN", ""),
            user_filter=os.environ.get("LDAP_USER_FILTER", "(uid={username})"),
            user_dn_template=os.environ.get("LDAP_USER_DN_TEMPLATE", ""),
            attribute_map=attribute_map,
        )


@dataclass
class JwtConfig:
    """JWT token configuration (shared with the OAuth2 plugin / dserver)."""

    private_key_file: str = "/app/jwt/jwt_key"
    public_key_file: str = "/app/jwt/jwt_key.pub"
    algorithm: str = "RS256"
    issuer: str = "dserver"
    audience: str = "dserver"
    token_expiry_hours: int = 24

    @classmethod
    def from_env(cls) -> "JwtConfig":
        """Create configuration from environment variables."""
        return cls(
            private_key_file=os.environ.get(
                "JWT_PRIVATE_KEY_FILE", "/app/jwt/jwt_key"
            ),
            public_key_file=os.environ.get(
                "JWT_PUBLIC_KEY_FILE", "/app/jwt/jwt_key.pub"
            ),
            algorithm=os.environ.get("JWT_ALGORITHM", "RS256"),
            issuer=os.environ.get("JWT_ISSUER", "dserver"),
            audience=os.environ.get("JWT_AUDIENCE", "dserver"),
            token_expiry_hours=int(os.environ.get("JWT_TOKEN_EXPIRY_HOURS", "24")),
        )


@dataclass
class PluginConfig:
    """Overall LDAP plugin configuration."""

    ldap: LdapProviderConfig = field(default_factory=LdapProviderConfig.from_env)
    jwt: JwtConfig = field(default_factory=JwtConfig.from_env)

    # On successful LDAP login, create the user in dserver's own table if
    # missing (LDAP does authentication; dserver's table does authorization).
    auto_provision_users: bool = True

    # Base URIs to grant the user search (and optionally register) permission
    # on at provision time, e.g. "s3://dtool-bucket" (comma-separated).
    default_base_uris: list = field(default_factory=list)

    # Whether to also grant register permission (not just search).
    grant_register: bool = True

    @classmethod
    def from_env(cls) -> "PluginConfig":
        """Create configuration from environment variables."""
        default_base_uris = [
            u.strip()
            for u in os.environ.get("LDAP_DEFAULT_BASE_URIS", "").split(",")
            if u.strip()
        ]
        return cls(
            ldap=LdapProviderConfig.from_env(),
            jwt=JwtConfig.from_env(),
            auto_provision_users=os.environ.get(
                "LDAP_AUTO_PROVISION_USERS", "true"
            ).lower() == "true",
            default_base_uris=default_base_uris,
            grant_register=os.environ.get(
                "LDAP_GRANT_REGISTER", "true"
            ).lower() == "true",
        )
