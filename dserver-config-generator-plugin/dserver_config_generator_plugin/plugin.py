"""
dserver plugin registration for the config generator.

Implements the dservercore ExtensionABC interface; loads alongside the other
extensions and owns the /config-generator blueprint prefix.
"""

import logging

from flask import Flask

from .blueprint import config_generator_bp
from .config import PluginConfig

logger = logging.getLogger(__name__)


class ConfigGeneratorPlugin:
    """Generate per-user dtool.json / readme templates on authenticated routes."""

    def __init__(self, app: Flask = None):
        self.app = app
        self.config: PluginConfig = None
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask, *args, **kwargs):
        self.app = app
        self.config = PluginConfig.from_env()
        logger.info(
            "Config-generator plugin initialized (credential provider: %s)",
            self.config.credential_provider,
        )

    def get_blueprint(self):
        return config_generator_bp

    def register_dataset(self, dataset_info):
        """No-op: required by dservercore PluginABC, unused here."""
        pass

    def get_config(self):
        return {}

    def get_config_secrets_to_obfuscate(self):
        # Names of secret-bearing env vars across providers (plain strings; no imports).
        return [
            "CONFIG_GENERATOR_STATIC_SECRET_KEY",
            "CONFIG_GENERATOR_MINIO_ADMIN_SECRET_KEY",
        ]

    @staticmethod
    def get_name() -> str:
        return "config-generator"

    @staticmethod
    def get_version() -> str:
        from . import __version__
        return __version__

    @staticmethod
    def get_description() -> str:
        return "Dynamic per-user dtool.json / readme template generator"
