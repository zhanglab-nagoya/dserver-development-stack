"""Environment-driven configuration for the SAML2 token generator.

Mirrors the OAuth2 plugin's config style. pysaml2 is imported lazily inside
``make_saml_config()`` so this module (and the pure helpers below) import without it.
"""
import os

AFFIRMATIVE = {"true", "1", "yes", "y", "on"}


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in AFFIRMATIVE


def parse_attribute_map(spec):
    """'eduPersonPrincipalName:user_id,mail:email' -> {'eduPersonPrincipalName': 'user_id', ...}"""
    result = {}
    for pair in (spec or "").split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        saml_attr, field = pair.split(":", 1)
        result[saml_attr.strip()] = field.strip()
    return result


class Config:
    # Public base URL where this SP is reachable, INCLUDING any WSGI SCRIPT_NAME prefix
    # (e.g. https://<your-host>/lookup). ACS/metadata/SLS URLs derive from it +
    # URL_PREFIX.
    BASE_URL = os.environ.get("SAML_BASE_URL", "http://localhost:5000")

    # Blueprint mount point (CONFIGURABLE). Defaults to /saml so it can run alongside the
    # OAuth2 plugin, which claims /auth. Set to /auth to drop-in replace it.
    URL_PREFIX = os.environ.get("SAML_URL_PREFIX", "/saml")

    # SP identity. Defaults to the metadata URL, a common convention.
    SP_ENTITY_ID = os.environ.get("SAML_SP_ENTITY_ID", "") or f"{BASE_URL}{URL_PREFIX}/metadata"

    # IdP / federation metadata: a URL (e.g. GakuNin federation feed) and/or a local file.
    IDP_METADATA_URL = os.environ.get("SAML_IDP_METADATA_URL", "")
    IDP_METADATA_FILE = os.environ.get("SAML_IDP_METADATA_FILE", "")
    # Optional: pin a specific IdP entityID (required when the metadata holds many IdPs,
    # e.g. the whole GakuNin federation, until a discovery service is wired in).
    IDP_ENTITY_ID = os.environ.get("SAML_IDP_ENTITY_ID", "")

    # SP signing/encryption keypair (PEM). GakuNin typically signs requests and encrypts
    # assertions, so both are usually required.
    SP_KEY_FILE = os.environ.get("SAML_SP_KEY_FILE", "")
    SP_CERT_FILE = os.environ.get("SAML_SP_CERT_FILE", "")

    XMLSEC_BINARY = os.environ.get("SAML_XMLSEC_BINARY", "/usr/bin/xmlsec1")

    AUTHN_REQUESTS_SIGNED = _bool(os.environ.get("SAML_AUTHN_REQUESTS_SIGNED"), True)
    WANT_RESPONSE_SIGNED = _bool(os.environ.get("SAML_WANT_RESPONSE_SIGNED"), True)
    WANT_ASSERTIONS_SIGNED = _bool(os.environ.get("SAML_WANT_ASSERTIONS_SIGNED"), True)
    ALLOW_UNSOLICITED = _bool(os.environ.get("SAML_ALLOW_UNSOLICITED"), False)

    # SAML attribute (friendly name) -> internal field. GakuNin: ePPN is the stable id.
    ATTRIBUTE_MAP = parse_attribute_map(
        os.environ.get(
            "SAML_ATTRIBUTE_MAP",
            "eduPersonPrincipalName:user_id,mail:email,displayName:display_name",
        )
    )
    USERNAME_FIELD = os.environ.get("SAML_USERNAME_FIELD", "user_id")

    # Frontend redirects after login (mirror the OAuth2 plugin).
    LOGIN_SUCCESS_REDIRECT = os.environ.get("SAML_LOGIN_SUCCESS_REDIRECT", BASE_URL)
    LOGIN_ERROR_REDIRECT = os.environ.get(
        "SAML_LOGIN_ERROR_REDIRECT", f"{BASE_URL}/login?error=auth_failed"
    )

    # JWT: reuse dserver's keypair so the issued token validates like any other.
    JWT_PRIVATE_KEY_FILE = os.environ.get("JWT_PRIVATE_KEY_FILE", "")
    JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "RS256")
    JWT_EXPIRY_HOURS = int(os.environ.get("SAML_JWT_EXPIRY_HOURS", "24"))


def acs_url():
    return f"{Config.BASE_URL}{Config.URL_PREFIX}/acs"


def sls_url():
    return f"{Config.BASE_URL}{Config.URL_PREFIX}/sls"


def metadata_url():
    return f"{Config.BASE_URL}{Config.URL_PREFIX}/metadata"


def make_saml_config():
    """Build and load a pysaml2 ``SPConfig`` from the env settings (imports pysaml2)."""
    from saml2 import BINDING_HTTP_POST, BINDING_HTTP_REDIRECT
    from saml2.config import SPConfig

    settings = {
        "entityid": Config.SP_ENTITY_ID,
        "xmlsec_binary": Config.XMLSEC_BINARY,
        "allow_unknown_attributes": True,
        "service": {
            "sp": {
                "name": "dserver SAML SP",
                "endpoints": {
                    "assertion_consumer_service": [(acs_url(), BINDING_HTTP_POST)],
                    "single_logout_service": [(sls_url(), BINDING_HTTP_REDIRECT)],
                },
                "allow_unsolicited": Config.ALLOW_UNSOLICITED,
                "authn_requests_signed": Config.AUTHN_REQUESTS_SIGNED,
                "want_response_signed": Config.WANT_RESPONSE_SIGNED,
                "want_assertions_signed": Config.WANT_ASSERTIONS_SIGNED,
            }
        },
    }

    metadata = {}
    if Config.IDP_METADATA_URL:
        metadata.setdefault("remote", []).append({"url": Config.IDP_METADATA_URL})
    if Config.IDP_METADATA_FILE:
        metadata.setdefault("local", []).append(Config.IDP_METADATA_FILE)
    if metadata:
        settings["metadata"] = metadata

    if Config.SP_KEY_FILE and Config.SP_CERT_FILE:
        settings["key_file"] = Config.SP_KEY_FILE
        settings["cert_file"] = Config.SP_CERT_FILE
        settings["encryption_keypairs"] = [
            {"key_file": Config.SP_KEY_FILE, "cert_file": Config.SP_CERT_FILE}
        ]

    conf = SPConfig()
    conf.load(settings)
    return conf
