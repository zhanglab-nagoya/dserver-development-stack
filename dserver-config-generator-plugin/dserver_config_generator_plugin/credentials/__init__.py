"""
Pluggable credential providers for the generated dtool.json.

A provider takes the authenticated username (plus a small context dict) and
returns the S3 credentials to embed — or an empty dict to embed none. Providers
are selected by name via ``CONFIG_GENERATOR_CREDENTIAL_PROVIDER`` and imported
**lazily**, so importing this plugin never imports a provider's dependencies
(e.g. ``minio``).

To add a provider: drop a module in this package exposing a CredentialProvider
subclass and register its name in ``_PROVIDER_MODULES``. To remove MinIO support
entirely: delete ``minio.py`` and its one line below — nothing else references it.
"""

import importlib
from abc import ABC, abstractmethod


class Credentials(dict):
    """Result of issue(): may be empty, or hold access_key/secret_key/expiration."""


class CredentialProvider(ABC):
    """Mints/looks up the S3 credentials embedded in a user's dtool.json."""

    @abstractmethod
    def issue(self, username: str, context: dict) -> Credentials:
        """Return Credentials for the user (possibly empty)."""
        raise NotImplementedError


# Provider name -> "module:ClassName" within this package. Lazy-imported.
_PROVIDER_MODULES = {
    "none": "none:NoneProvider",
    "static": "static:StaticProvider",
    "minio": "minio:MinioServiceAccountProvider",
}


def get_provider(name: str) -> CredentialProvider:
    """Instantiate the named provider, importing its module lazily."""
    key = (name or "none").lower()
    if key not in _PROVIDER_MODULES:
        raise ValueError(
            f"Unknown credential provider '{name}'. "
            f"Available: {', '.join(sorted(_PROVIDER_MODULES))}"
        )
    module_name, class_name = _PROVIDER_MODULES[key].split(":")
    module = importlib.import_module(f"{__name__}.{module_name}")
    return getattr(module, class_name)()


__all__ = ["Credentials", "CredentialProvider", "get_provider"]
