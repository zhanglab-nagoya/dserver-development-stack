"""
dserver plugin registration for the LDAP token generator.

Integrates with dservercore's plugin discovery via the ExtensionABC interface
(entry-point group ``dservercore.extension``). Loads alongside the OAuth2
plugin; this one owns the ``/auth/ldap`` blueprint prefix.
"""

import logging

from flask import Flask

from .blueprint import ldap_bp
from .config import PluginConfig

logger = logging.getLogger(__name__)


class LdapTokenGeneratorPlugin:
    """
    LDAP username/password token generator plugin for dserver.

    Implements the dservercore ExtensionABC interface.
    """

    def __init__(self, app: Flask = None):
        self.app = app
        self.config: PluginConfig = None

        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask, *args, **kwargs):
        """Initialize the plugin with a Flask application (called by app factory)."""
        self.app = app
        self.config = PluginConfig.from_env()

        logger.info("LDAP Token Generator plugin initialized")
        if self.config.ldap.uri:
            logger.info("LDAP URI: %s", self.config.ldap.uri)
        else:
            logger.warning("LDAP not configured - LDAP_URI not set")

    def get_blueprint(self):
        """Return the Flask blueprint for this extension (required)."""
        return ldap_bp

    def register_dataset(self, dataset_info):
        """No-op: required by dservercore PluginABC, unused for auth."""
        pass

    def get_config(self):
        """Return plugin configuration dictionary (required by PluginABC)."""
        return {}

    def get_config_secrets_to_obfuscate(self):
        """Return config keys that should not be exposed in logs/config dumps."""
        return ["LDAP_BIND_PASSWORD"]

    @staticmethod
    def get_name() -> str:
        return "ldap-token-generator"

    @staticmethod
    def get_version() -> str:
        from . import __version__
        return __version__

    @staticmethod
    def get_description() -> str:
        return "LDAP username/password token generator for dserver"
