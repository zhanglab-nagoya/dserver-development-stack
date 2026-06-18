"""Route smoke test — needs dservercore + flask_smorest (runs in the container)."""

import json

import pytest

pytest.importorskip("dservercore")
pytest.importorskip("flask_smorest")


@pytest.fixture
def client(monkeypatch):
    from flask import Flask
    from flask_smorest import Api
    import dserver_config_generator_plugin.blueprint as bp

    monkeypatch.setenv("CONFIG_GENERATOR_CREDENTIAL_PROVIDER", "none")
    bp._config = None

    # Run with JWT auth disabled and stub out the dservercore lookups.
    monkeypatch.setattr(bp, "get_jwt_identity", lambda: "testuser")
    monkeypatch.setattr(bp, "user_exists", lambda u: True)
    monkeypatch.setattr(bp, "get_user_info", lambda u: {"display_name": "Test User"})
    monkeypatch.setattr(bp, "list_search_base_uris", lambda u: ["s3://dtool-bucket"])
    monkeypatch.setattr(bp, "list_register_base_uris", lambda u: ["s3://dtool-bucket"])

    app = Flask(__name__)
    app.config.update(
        API_TITLE="t", API_VERSION="v1", OPENAPI_VERSION="3.0.2",
        DISABLE_JWT_AUTHORISATION=True, DEFAULT_USER="testuser",
    )
    api = Api(app)
    api.register_blueprint(bp.config_generator_bp)
    return app.test_client()


def test_dtool_json_route(client):
    resp = client.get("/config-generator/dtool.json")
    assert resp.status_code == 200
    assert "attachment;filename=dtool.json" in resp.headers["Content-Disposition"]
    data = json.loads(resp.data)
    assert data["DSERVER_USERNAME"] == "testuser"
    assert data["DTOOL_S3_DATASET_PREFIX"] == "u/testuser/"
    assert "DTOOL_S3_SECRET_ACCESS_KEY_dtool-bucket" not in data  # none provider


def test_readme_route(client):
    resp = client.get("/config-generator/dtool_readme.yml")
    assert resp.status_code == 200
    assert "attachment;filename=dtool_readme.yml" in resp.headers["Content-Disposition"]
    assert b"username: testuser" in resp.data


def test_info_route(client):
    resp = client.get("/config-generator/info")
    assert resp.status_code == 200
    assert resp.get_json()["credential_provider"] == "none"
