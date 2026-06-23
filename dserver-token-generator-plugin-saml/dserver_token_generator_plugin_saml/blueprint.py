"""SAML 2.0 SP Flask blueprint for dserver (pysaml2-based).

Routes (under the configurable ``SAML_URL_PREFIX``, default ``/saml``):
  GET  /login     -> redirect to the IdP carrying a SAML AuthnRequest
  POST /acs       -> Assertion Consumer Service: validate the IdP's signed Response,
                     map attributes -> username, mint a dserver JWT, redirect to the frontend
  GET  /metadata  -> this SP's SAML metadata XML (register it with NII/GakuNin)
  GET  /sls       -> Single Logout (best-effort local session clear for now)
  GET  /info      -> provider info for the webapp login screen

The pysaml2 client is built per-request from env config; the security-sensitive XML
signature / assertion validation is handled by pysaml2.
"""
import logging

from flask import request, redirect, jsonify, session, make_response
from flask_smorest import Blueprint

from .config import Config, make_saml_config
from . import jwt_utils

logger = logging.getLogger(__name__)

# url_prefix is read from the environment at import time (configurable).
bp = Blueprint("saml_auth", __name__, url_prefix=Config.URL_PREFIX)


def _client():
    from saml2.client import Saml2Client
    return Saml2Client(config=make_saml_config())


@bp.route("/login")
def login():
    """Initiate SAML login: build an AuthnRequest and redirect to the IdP."""
    try:
        client = _client()
        next_url = request.args.get("next", Config.LOGIN_SUCCESS_REDIRECT)
        kwargs = {}
        if Config.IDP_ENTITY_ID:
            # Pin the IdP when the metadata contains several (e.g. the GakuNin federation).
            kwargs["entityid"] = Config.IDP_ENTITY_ID

        req_id, info = client.prepare_for_authenticate(relay_state=next_url, **kwargs)

        # Remember the outstanding request id for InResponseTo validation at the ACS.
        outstanding = session.get("saml_outstanding", {})
        outstanding[req_id] = next_url
        session["saml_outstanding"] = outstanding
        session.modified = True

        for key, value in info.get("headers", []):
            if key == "Location":
                return redirect(value)
        logger.error("Could not extract redirect Location from AuthnRequest")
        return redirect(Config.LOGIN_ERROR_REDIRECT)
    except Exception:
        logger.exception("SAML login initiation failed")
        return redirect(Config.LOGIN_ERROR_REDIRECT)


@bp.route("/acs", methods=["POST"])
def acs():
    """Assertion Consumer Service: consume and validate the IdP's SAML Response."""
    from saml2 import BINDING_HTTP_POST

    saml_response = request.form.get("SAMLResponse")
    if not saml_response:
        return jsonify({"error": "Missing SAMLResponse"}), 400

    try:
        client = _client()
        outstanding = session.get("saml_outstanding", {})
        authn_response = client.parse_authn_request_response(
            saml_response, BINDING_HTTP_POST, outstanding=outstanding
        )
        if authn_response is None:
            logger.error("SAML response failed validation")
            return redirect(Config.LOGIN_ERROR_REDIRECT)

        identity = authn_response.get_identity()  # {saml_attr: [values]}
        username, fields = jwt_utils.map_identity(
            identity, Config.ATTRIBUTE_MAP, Config.USERNAME_FIELD
        )

        if not username:
            # Fall back to the SAML NameID subject if the username attribute is absent.
            try:
                username = authn_response.get_subject().text
            except Exception:
                username = None

        if not username:
            logger.error(
                "No username in SAML assertion (wanted field %r); attributes present: %s",
                Config.USERNAME_FIELD, list((identity or {}).keys()),
            )
            return redirect(Config.LOGIN_ERROR_REDIRECT)

        token = jwt_utils.mint_token(
            Config.JWT_PRIVATE_KEY_FILE,
            Config.JWT_ALGORITHM,
            username,
            expiry_hours=Config.JWT_EXPIRY_HOURS,
            name=fields.get("display_name"),
            email=fields.get("email"),
            extra={"provider_user_id": username},
        )

        relay = request.form.get("RelayState") or Config.LOGIN_SUCCESS_REDIRECT
        separator = "&" if "?" in relay else "?"
        response = make_response(redirect(f"{relay}{separator}token={token}"))
        response.set_cookie(
            "dserver_token", token,
            httponly=False, secure=request.is_secure, samesite="Lax",
            max_age=Config.JWT_EXPIRY_HOURS * 3600,
        )
        session.pop("saml_outstanding", None)
        logger.info("SAML login succeeded for %s", username)
        return response
    except Exception:
        logger.exception("SAML ACS processing failed")
        return redirect(Config.LOGIN_ERROR_REDIRECT)


@bp.route("/metadata")
def metadata():
    """Serve this SP's SAML metadata (register it with the federation / IdP)."""
    from saml2.metadata import entity_descriptor

    entity_desc = entity_descriptor(make_saml_config())
    response = make_response(str(entity_desc))
    response.headers["Content-Type"] = "application/xml"
    return response


@bp.route("/sls")
def sls():
    """Single Logout — best-effort local clear for now (full IdP-driven SLO is a TODO)."""
    session.clear()
    return redirect(Config.LOGIN_SUCCESS_REDIRECT)


@bp.route("/info")
def info():
    """Provider info for the webapp (mirrors the OAuth2 plugin's /auth/info)."""
    configured = bool(Config.IDP_METADATA_URL or Config.IDP_METADATA_FILE)
    return jsonify({
        "configured": configured,
        "provider": "saml",
        "login_url": f"{Config.BASE_URL}{Config.URL_PREFIX}/login",
    })
