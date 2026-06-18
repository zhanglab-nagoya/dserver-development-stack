"""
Flask blueprint exposing the dynamic config-generator routes (prefix
``/config-generator``):

- GET /config-generator/dtool.json        -> per-user dtool config (attachment)
- GET /config-generator/dtool_readme.yml  -> per-user readme template (attachment)
- GET /config-generator/info              -> non-secret diagnostics
"""

import logging

from flask import abort, current_app, jsonify
from flask_smorest import Blueprint

from dservercore.utils import get_user_info
from dservercore.utils_auth import (
    get_jwt_identity,
    jwt_required,
    list_register_base_uris,
    list_search_base_uris,
    user_exists,
)

from .config import PluginConfig
from .generator import build_context, generate_dtool_json, generate_readme

logger = logging.getLogger(__name__)

config_generator_bp = Blueprint(
    "config_generator",
    __name__,
    url_prefix="/config-generator",
    description="Dynamic per-user dtool.json / readme template generation",
)

_config: PluginConfig = None


def get_config() -> PluginConfig:
    global _config
    if _config is None:
        _config = PluginConfig.from_env()
    return _config


def _context_for_current_user() -> dict:
    username = get_jwt_identity()
    if not user_exists(username):
        abort(401)
    info = get_user_info(username) or {}
    config = get_config()
    return build_context(
        config,
        username,
        info.get("display_name") or username,
        list_search_base_uris(username),
        list_register_base_uris(username),
    )


@config_generator_bp.route("/dtool.json", methods=["GET"])
@jwt_required()
def dtool_json():
    """Generate this user's dtool.json (mints credentials via the active provider)."""
    config = get_config()
    ctx = _context_for_current_user()
    body = generate_dtool_json(config, ctx)
    return current_app.response_class(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=dtool.json"},
    )


@config_generator_bp.route("/dtool_readme.yml", methods=["GET"])
@jwt_required()
def dtool_readme():
    """Generate this user's dtool README template."""
    config = get_config()
    ctx = _context_for_current_user()
    body = generate_readme(config, ctx)
    return current_app.response_class(
        body,
        mimetype="application/x-yaml",
        headers={"Content-Disposition": "attachment;filename=dtool_readme.yml"},
    )


@config_generator_bp.route("/info", methods=["GET"])
def info():
    """Non-secret diagnostics."""
    config = get_config()
    return jsonify({
        "credential_provider": config.credential_provider,
        "s3_public_endpoint": config.s3_public_endpoint,
        "s3_bucket": config.s3_bucket,
        "dtool_json_url": "/config-generator/dtool.json",
        "dtool_readme_url": "/config-generator/dtool_readme.yml",
    })
