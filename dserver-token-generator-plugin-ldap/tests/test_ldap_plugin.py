"""Unit tests for the LDAP token generator (LDAP itself is mocked)."""

import jwt


def _patch_auth(monkeypatch, result):
    """Make the authenticator return a fixed result without touching LDAP."""
    import dserver_token_generator_plugin_ldap.blueprint as bp

    class FakeAuth:
        def authenticate(self, username, password):
            return result

    monkeypatch.setattr(bp, "_authenticator", FakeAuth())


def test_missing_body_returns_400(client):
    resp = client.post("/auth/ldap/token")
    assert resp.status_code == 400


def test_missing_password_returns_400(client):
    resp = client.post("/auth/ldap/token", json={"username": "alice"})
    assert resp.status_code == 400


def test_bad_credentials_return_401(client, monkeypatch):
    _patch_auth(monkeypatch, None)
    resp = client.post(
        "/auth/ldap/token", json={"username": "alice", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_valid_credentials_mint_token(client, monkeypatch, rsa_key_files):
    _patch_auth(monkeypatch, {"email": "alice@example.org", "display_name": "Alice"})
    resp = client.post(
        "/auth/ldap/token", json={"username": "alice", "password": "secret"}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "alice"
    assert body["token_type"] == "Bearer"

    # Token is a valid RS256 JWT with sub == username.
    _, pub = rsa_key_files
    decoded = jwt.decode(
        body["token"],
        open(pub).read(),
        algorithms=["RS256"],
        audience="dserver",
        issuer="dserver",
    )
    assert decoded["sub"] == "alice"
    assert decoded["email"] == "alice@example.org"


def test_info_endpoint(client):
    resp = client.get("/auth/ldap/info")
    assert resp.status_code == 200
    assert resp.get_json()["provider"] == "ldap"
