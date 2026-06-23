"""
dserver-token-generator-plugin-ldap

A simple username/password token generator plugin for dserver that
authenticates credentials against an LDAP directory and issues RS256 JWTs.

Modeled on dserver-token-generator-plugin-oauth2 so both can be loaded as
dservercore extensions at the same time (this one owns the ``/auth/ldap``
prefix; the OAuth2 plugin owns ``/auth/oauth2``).
"""

__version__ = "0.1.0"

from .plugin import LdapTokenGeneratorPlugin
from .blueprint import ldap_bp

__all__ = ["LdapTokenGeneratorPlugin", "ldap_bp", "__version__"]
