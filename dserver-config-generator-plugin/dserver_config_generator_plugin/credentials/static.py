"""Static provider: embed operator-configured shared S3 credentials.

MinIO-free. Reads its own env so the plugin core stays provider-agnostic.
"""

import os

from . import CredentialProvider, Credentials


class StaticProvider(CredentialProvider):
    def issue(self, username: str, context: dict) -> Credentials:
        access_key = os.environ.get("CONFIG_GENERATOR_STATIC_ACCESS_KEY", "")
        secret_key = os.environ.get("CONFIG_GENERATOR_STATIC_SECRET_KEY", "")
        if not access_key or not secret_key:
            return Credentials()
        return Credentials(access_key=access_key, secret_key=secret_key)
