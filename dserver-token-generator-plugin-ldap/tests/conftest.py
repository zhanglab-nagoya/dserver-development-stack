"""Test fixtures: RSA keys + a minimal Flask app with the LDAP blueprint."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def rsa_key_files(tmp_path):
    """Generate an RSA key pair for JWT signing/verification."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = tmp_path / "jwt_key"
    pub = tmp_path / "jwt_key.pub"
    priv.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return str(priv), str(pub)


@pytest.fixture
def app(monkeypatch, rsa_key_files):
    """Flask app with the LDAP blueprint registered and module globals reset."""
    from flask import Flask
    from flask_smorest import Api

    priv, pub = rsa_key_files
    monkeypatch.setenv("JWT_PRIVATE_KEY_FILE", priv)
    monkeypatch.setenv("JWT_PUBLIC_KEY_FILE", pub)
    monkeypatch.setenv("LDAP_URI", "ldap://localhost:389")
    monkeypatch.setenv("LDAP_AUTO_PROVISION_USERS", "false")  # no DB in unit tests

    # Reset lazily-initialized singletons so env changes take effect.
    import dserver_token_generator_plugin_ldap.blueprint as bp
    bp._config = None
    bp._jwt_generator = None
    bp._authenticator = None
    bp._user_provisioner = None

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["API_TITLE"] = "test"
    app.config["API_VERSION"] = "v1"
    app.config["OPENAPI_VERSION"] = "3.0.2"
    api = Api(app)
    api.register_blueprint(bp.ldap_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()
