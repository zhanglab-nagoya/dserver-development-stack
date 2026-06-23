"""Native SAML 2.0 token generator plugin for dserver (Shibboleth-compatible).

A dservercore extension, sibling to ``dserver-token-generator-plugin-oauth2``: it
authenticates users against a SAML 2.0 Identity Provider (e.g. an institutional
Shibboleth IdP, or a federation IdP such as one of the GakuNin federation members in
Japan) and mints a dserver-compatible RS256 JWT — so dserver validates it exactly like a
token from any other generator.

Activation needs (see README.md):
  - the system ``xmlsec1`` binary + ``libxmlsec1`` (pysaml2 dependency),
  - IdP/federation metadata and an SP signing keypair,
  - registration of this SP's metadata with the federation operator and/or the
    institutional IdP admin + attribute release (eduPersonPrincipalName etc.).

The SAML-heavy imports are deferred to ``get_blueprint()`` so this module imports even
before pysaml2 is installed.
"""
__version__ = "0.1.0"

import logging

logger = logging.getLogger(__name__)


class SamlTokenGeneratorPlugin:
    """dservercore ExtensionABC-compatible SAML2 token generator."""

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app, *args, **kwargs):
        logger.info("SamlTokenGeneratorPlugin loaded (SAML2 SP).")

    def get_blueprint(self):
        # Lazy import: pulls in pysaml2 only when dserver actually mounts the blueprint.
        from .blueprint import bp
        return bp

    def get_config(self):
        return {}

    def get_config_secrets_to_obfuscate(self):
        return ["SAML_SP_KEY_FILE", "JWT_PRIVATE_KEY_FILE"]
