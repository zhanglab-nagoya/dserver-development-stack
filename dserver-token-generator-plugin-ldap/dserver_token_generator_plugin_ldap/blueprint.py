"""
Flask blueprint for LDAP username/password authentication.

Endpoints (under the ``/auth/ldap`` prefix):
- POST /auth/ldap/token - exchange {username, password} for a JWT
- GET  /auth/ldap/info  - non-secret diagnostics

The POST handler matches the contract the dtool-lookup-webapp's
username/password form expects: it accepts JSON ``{"username", "password"}``
and returns ``{"token", "username", "token_type"}``.
"""

import logging

from flask import jsonify, request
from flask_smorest import Blueprint

from .config import PluginConfig
from .jwt_utils import JwtTokenGenerator
from .ldap_auth import LdapAuthenticator
from .user_provisioning import UserProvisioner

logger = logging.getLogger(__name__)

# Must be a flask_smorest Blueprint (dservercore rejects plain flask.Blueprint).
ldap_bp = Blueprint(
    "ldap_auth",
    __name__,
    url_prefix="/auth/ldap",
    description="LDAP username/password authentication endpoints",
)

# Lazily-initialized singletons (mirrors the OAuth2 plugin).
_config: PluginConfig = None
_jwt_generator: JwtTokenGenerator = None
_authenticator: LdapAuthenticator = None
_user_provisioner: UserProvisioner = None


def get_config() -> PluginConfig:
    global _config
    if _config is None:
        _config = PluginConfig.from_env()
    return _config


def get_jwt_generator() -> JwtTokenGenerator:
    global _jwt_generator
    if _jwt_generator is None:
        _jwt_generator = JwtTokenGenerator(get_config().jwt)
    return _jwt_generator


def get_authenticator() -> LdapAuthenticator:
    global _authenticator
    if _authenticator is None:
        _authenticator = LdapAuthenticator(get_config().ldap)
    return _authenticator


def get_user_provisioner() -> UserProvisioner:
    global _user_provisioner
    if _user_provisioner is None:
        config = get_config()
        _user_provisioner = UserProvisioner(
            auto_provision=config.auto_provision_users,
            default_base_uris=config.default_base_uris,
            grant_register=config.grant_register,
        )
    return _user_provisioner


@ldap_bp.route("/token", methods=["POST"])
def create_token():
    """Exchange LDAP username/password for a dserver JWT."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400

    user_attrs = get_authenticator().authenticate(username, password)
    if user_attrs is None:
        logger.info("LDAP authentication failed for user: %s", username)
        return jsonify({"error": "Invalid credentials"}), 401

    # Authentication succeeded; ensure the user is known + permitted in dserver.
    try:
        get_user_provisioner().provision_user(
            username,
            email=user_attrs.get("email"),
            display_name=user_attrs.get("display_name"),
        )
    except Exception:  # pragma: no cover - provisioning must not 500 the login
        logger.exception("LDAP: provisioning failed for %s", username)

    token = get_jwt_generator().generate_token(
        username=username,
        email=user_attrs.get("email"),
        display_name=user_attrs.get("display_name"),
        permissions=["search", "retrieve"],
    )

    logger.info("LDAP: issued token for user %s", username)
    return jsonify({
        "token": token,
        "username": username,
        "token_type": "Bearer",
    })


@ldap_bp.route("/info", methods=["GET"])
def info():
    """Return non-secret configuration diagnostics."""
    config = get_config()
    return jsonify({
        "provider": "ldap",
        "configured": bool(config.ldap.uri),
        "token_url": request.host_url.rstrip("/") + "/auth/ldap/token",
        "auto_provision_users": config.auto_provision_users,
    })
