"""Generator tests — no Flask / dservercore needed."""

import json

from dserver_config_generator_plugin.config import PluginConfig
from dserver_config_generator_plugin.generator import (
    build_context,
    generate_dtool_json,
    generate_readme,
)


def _cfg(provider="none"):
    return PluginConfig(
        credential_provider=provider,
        s3_public_endpoint="http://localhost:9000",
        s3_bucket="dtool-bucket",
        dataset_prefix_template="u/{username}/",
        dserver_url="http://localhost:5000",
        token_generator_url="http://localhost:5000/auth/ldap/token",
        default_base_uri="s3://dtool-bucket",
    )


def test_dtool_json_none_provider_has_no_secret():
    cfg = _cfg("none")
    ctx = build_context(cfg, "testuser", "Test User", ["s3://dtool-bucket"], [])
    data = json.loads(generate_dtool_json(cfg, ctx))
    assert data["DSERVER_USERNAME"] == "testuser"
    assert data["DTOOL_S3_DATASET_PREFIX"] == "u/testuser/"
    assert data["DTOOL_S3_ENDPOINT_dtool-bucket"] == "http://localhost:9000"
    assert "DTOOL_S3_SECRET_ACCESS_KEY_dtool-bucket" not in data
    assert "DTOOL_S3_ACCESS_KEY_ID_dtool-bucket" not in data


def test_dtool_json_static_provider_embeds_keys(monkeypatch):
    monkeypatch.setenv("CONFIG_GENERATOR_STATIC_ACCESS_KEY", "AK")
    monkeypatch.setenv("CONFIG_GENERATOR_STATIC_SECRET_KEY", "SK")
    cfg = _cfg("static")
    ctx = build_context(cfg, "testuser", "Test User", [], [])
    data = json.loads(generate_dtool_json(cfg, ctx))
    assert data["DTOOL_S3_ACCESS_KEY_ID_dtool-bucket"] == "AK"
    assert data["DTOOL_S3_SECRET_ACCESS_KEY_dtool-bucket"] == "SK"


def test_readme_is_personalized():
    cfg = _cfg("none")
    ctx = build_context(cfg, "0000-0001-2345-6789", "Jane Doe", [], [])
    out = generate_readme(cfg, ctx)
    assert "username: 0000-0001-2345-6789" in out
    assert "name: Jane Doe" in out
    # ORCID-looking username is surfaced as the orcid field
    assert "orcid: 0000-0001-2345-6789" in out
