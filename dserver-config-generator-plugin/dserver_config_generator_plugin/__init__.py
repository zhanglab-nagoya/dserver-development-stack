"""
dserver-config-generator-plugin

A dservercore extension that dynamically generates per-user dtool configuration
(dtool.json) and a dtool README template (dtool_readme.yml) on authenticated
routes, instead of serving static files.

S3 credentials embedded in the generated dtool.json come from a pluggable
credential provider (none | static | minio); see the `credentials` subpackage.
The plugin runs without MinIO by default — MinIO is an optional, isolated
provider behind the `minio` extra.
"""

__version__ = "0.1.0"

from .plugin import ConfigGeneratorPlugin
from .blueprint import config_generator_bp

__all__ = ["ConfigGeneratorPlugin", "config_generator_bp", "__version__"]
