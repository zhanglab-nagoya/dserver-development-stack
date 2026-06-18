"""
Build the per-user template context and render dtool.json / dtool_readme.yml.

Kept free of dservercore imports: the caller (blueprint) supplies the username,
display name and base-URI lists. dtool.json is built as a dict (so secret keys
are emitted only when a provider returns them); the readme is a Jinja2 template.
Both can be overridden with operator-provided Jinja2 files via config.
"""

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import PluginConfig
from .credentials import get_provider

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def build_context(
    config: PluginConfig,
    username: str,
    display_name: str,
    search_uris: list,
    register_uris: list,
) -> dict:
    """Assemble the render context, minting credentials via the active provider."""
    prefix = config.dataset_prefix(username)
    provider = get_provider(config.credential_provider)
    creds = provider.issue(username, {"bucket": config.s3_bucket, "prefix": prefix})
    return {
        "user": {
            "username": username,
            "display_name": display_name or username,
            # ORCID iD only if the username looks like one (ORCID logins use it).
            "orcid": username if _ORCID_RE.match(username or "") else "",
            "email": "",
        },
        "creds": dict(creds),
        "s3": {
            "public_endpoint": config.s3_public_endpoint,
            "bucket": config.s3_bucket,
            "prefix": prefix,
        },
        "server": {
            "url": config.dserver_url,
            "token_generator_url": config.token_generator_url,
            "default_base_uri": config.default_base_uri,
        },
        "base_uris": {"search": search_uris or [], "register": register_uris or []},
    }


def generate_dtool_json(config: PluginConfig, ctx: dict) -> str:
    if config.dtool_json_template:
        return _render_file(config.dtool_json_template, ctx)

    bucket = ctx["s3"]["bucket"]
    data = {
        "DSERVER_URL": ctx["server"]["url"],
        "DSERVER_TOKEN_GENERATOR_URL": ctx["server"]["token_generator_url"],
        "DSERVER_USERNAME": ctx["user"]["username"],
        "DSERVER_DEFAULT_BASE_URI": ctx["server"]["default_base_uri"],
        f"DTOOL_S3_ENDPOINT_{bucket}": ctx["s3"]["public_endpoint"],
        "DTOOL_S3_DATASET_PREFIX": ctx["s3"]["prefix"],
        "DTOOL_USER_FULL_NAME": ctx["user"]["display_name"],
        "DTOOL_USER_EMAIL": ctx["user"]["email"] or "you@your-institution.example",
        "DTOOL_README_TEMPLATE_FPATH": "~/.dtool/dtool_readme.yml",
    }
    creds = ctx["creds"]
    if creds.get("access_key") and creds.get("secret_key"):
        data[f"DTOOL_S3_ACCESS_KEY_ID_{bucket}"] = creds["access_key"]
        data[f"DTOOL_S3_SECRET_ACCESS_KEY_{bucket}"] = creds["secret_key"]
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def generate_readme(config: PluginConfig, ctx: dict) -> str:
    if config.readme_template:
        return _render_file(config.readme_template, ctx)
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=False)
    return env.get_template("dtool_readme.yml.j2").render(**ctx)


def _render_file(path: str, ctx: dict) -> str:
    p = Path(path)
    env = Environment(loader=FileSystemLoader(str(p.parent)), autoescape=False)
    return env.get_template(p.name).render(**ctx)
