"""Provider tests — no Flask / dservercore needed."""

import pytest

from dserver_config_generator_plugin.credentials import get_provider, Credentials


def test_none_provider_returns_empty():
    creds = get_provider("none").issue("alice", {"bucket": "b", "prefix": "u/alice/"})
    assert creds == {}


def test_static_provider_reads_env(monkeypatch):
    monkeypatch.setenv("CONFIG_GENERATOR_STATIC_ACCESS_KEY", "AK")
    monkeypatch.setenv("CONFIG_GENERATOR_STATIC_SECRET_KEY", "SK")
    creds = get_provider("static").issue("alice", {"bucket": "b", "prefix": "u/alice/"})
    assert creds == {"access_key": "AK", "secret_key": "SK"}


def test_static_provider_empty_without_env(monkeypatch):
    monkeypatch.delenv("CONFIG_GENERATOR_STATIC_ACCESS_KEY", raising=False)
    monkeypatch.delenv("CONFIG_GENERATOR_STATIC_SECRET_KEY", raising=False)
    assert get_provider("static").issue("a", {"bucket": "b", "prefix": "p"}) == {}


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_provider("bogus")


def test_minio_provider_is_lazy_and_registered():
    # Importing the registry must not require `minio`; resolving the class only
    # imports the module (which itself lazy-imports minio inside issue()).
    provider = get_provider("minio")
    assert provider.__class__.__name__ == "MinioServiceAccountProvider"
