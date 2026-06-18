"""
Configuration for the config-generator plugin.

Only provider-agnostic ("core") settings live here. Provider-specific settings
(e.g. MinIO admin credentials) are read by the provider module itself from the
environment, so this file — and the plugin core — never reference MinIO.
"""

import os
from dataclasses import dataclass


@dataclass
class PluginConfig:
    """Core, provider-agnostic configuration."""

    # Which credential provider mints the S3 keys embedded in dtool.json.
    credential_provider: str = "none"  # none | static | minio

    # Host-facing S3 endpoint written into the generated dtool.json (NOT the
    # internal endpoint a provider might use for admin calls).
    s3_public_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "dtool-bucket"
    dataset_prefix_template: str = "u/{username}/"

    # dserver-facing values for the generated config.
    dserver_url: str = "http://localhost:5000"
    token_generator_url: str = "http://localhost:5000/auth/ldap/token"
    default_base_uri: str = "s3://dtool-bucket"

    # Optional overrides for the bundled Jinja2 templates (filesystem paths).
    dtool_json_template: str = ""
    readme_template: str = ""

    @classmethod
    def from_env(cls) -> "PluginConfig":
        def env(name, default):
            return os.environ.get(name, default)

        return cls(
            credential_provider=env("CONFIG_GENERATOR_CREDENTIAL_PROVIDER", "none").lower(),
            s3_public_endpoint=env("CONFIG_GENERATOR_S3_PUBLIC_ENDPOINT", "http://localhost:9000"),
            s3_bucket=env("CONFIG_GENERATOR_S3_BUCKET", "dtool-bucket"),
            dataset_prefix_template=env("CONFIG_GENERATOR_DATASET_PREFIX_TEMPLATE", "u/{username}/"),
            dserver_url=env("CONFIG_GENERATOR_DSERVER_URL", "http://localhost:5000"),
            token_generator_url=env(
                "CONFIG_GENERATOR_TOKEN_GENERATOR_URL", "http://localhost:5000/auth/ldap/token"
            ),
            default_base_uri=env("CONFIG_GENERATOR_DEFAULT_BASE_URI", "s3://dtool-bucket"),
            dtool_json_template=env("CONFIG_GENERATOR_DTOOL_JSON_TEMPLATE", ""),
            readme_template=env("CONFIG_GENERATOR_README_TEMPLATE", ""),
        )

    def dataset_prefix(self, username: str) -> str:
        return self.dataset_prefix_template.format(username=username)
