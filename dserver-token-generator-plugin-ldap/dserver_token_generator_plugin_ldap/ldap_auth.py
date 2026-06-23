"""
LDAP authentication.

Validates a username/password against an LDAP directory and returns the
mapped user attributes on success, or None on failure. Supports two modes:

- search-then-bind (default): bind with a service account (or anonymously),
  search ``LDAP_USER_BASE_DN`` with ``LDAP_USER_FILTER`` to find the user's
  DN, then re-bind as that DN with the supplied password.
- direct-bind: build the user DN from ``LDAP_USER_DN_TEMPLATE`` and bind.
"""

import logging
import ssl
from typing import Optional

from ldap3 import Server, Connection, ALL, SUBTREE, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from .config import LdapProviderConfig

logger = logging.getLogger(__name__)


class LdapAuthenticator:
    """Authenticate users against an LDAP directory."""

    def __init__(self, config: LdapProviderConfig):
        self.config = config

    def _server(self) -> Server:
        tls = None
        if self.config.use_ssl or self.config.start_tls:
            # Dev default: do not verify the directory's certificate. Tighten
            # for production by configuring a proper Tls() object.
            tls = Tls(validate=ssl.CERT_NONE)
        return Server(
            self.config.uri,
            use_ssl=self.config.use_ssl,
            get_info=ALL,
            tls=tls,
        )

    def _bind(self, user: Optional[str], password: Optional[str]) -> Optional[Connection]:
        """Open a connection and bind. Returns the bound Connection or None."""
        server = self._server()
        conn = Connection(server, user=user or None, password=password or None)
        try:
            if self.config.start_tls and not self.config.use_ssl:
                conn.open()
                conn.start_tls()
            if not conn.bind():
                logger.debug("LDAP bind failed for %r: %s", user, conn.result)
                return None
        except LDAPException as exc:
            logger.warning("LDAP bind error for %r: %s", user, exc)
            return None
        return conn

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """
        Return mapped user attributes if credentials are valid, else None.

        Empty passwords are rejected outright (LDAP "unauthenticated bind"
        would otherwise succeed against some servers).
        """
        if not username or not password:
            return None

        if not self.config.uri:
            logger.error("LDAP_URI is not configured; cannot authenticate")
            return None

        try:
            if self.config.user_dn_template:
                return self._direct_bind(username, password)
            return self._search_then_bind(username, password)
        except LDAPException as exc:
            logger.warning("LDAP error authenticating %r: %s", username, exc)
            return None

    def _direct_bind(self, username: str, password: str) -> Optional[dict]:
        user_dn = self.config.user_dn_template.format(username=username)
        conn = self._bind(user_dn, password)
        if conn is None:
            return None
        attrs = self._read_attrs(conn, user_dn)
        conn.unbind()
        return self._map_attrs(attrs)

    def _search_then_bind(self, username: str, password: str) -> Optional[dict]:
        if not self.config.user_base_dn:
            logger.error("LDAP_USER_BASE_DN is required for search-then-bind")
            return None

        service = self._bind(self.config.bind_dn, self.config.bind_password)
        if service is None:
            logger.warning("LDAP service/anonymous bind failed")
            return None

        search_filter = self.config.user_filter.format(
            username=escape_filter_chars(username)
        )
        requested = list(self.config.attribute_map.keys())
        service.search(
            self.config.user_base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=requested,
        )
        entries = service.entries
        if not entries:
            logger.info("LDAP: no entry for username %r", username)
            service.unbind()
            return None
        if len(entries) > 1:
            logger.warning("LDAP: %d entries matched %r; using first",
                           len(entries), username)

        entry = entries[0]
        user_dn = entry.entry_dn
        attrs = {
            attr: entry[attr].value
            for attr in requested
            if attr in entry and entry[attr].value is not None
        }
        service.unbind()

        # Verify the password by binding as the located DN.
        user_conn = self._bind(user_dn, password)
        if user_conn is None:
            logger.info("LDAP: password bind failed for %r (%s)", username, user_dn)
            return None
        user_conn.unbind()

        return self._map_attrs(attrs)

    @staticmethod
    def _read_attrs(conn: Connection, user_dn: str) -> dict:
        """Read mapped attributes from the user's own entry (direct-bind mode)."""
        try:
            conn.search(user_dn, "(objectClass=*)", search_scope="BASE",
                        attributes=["*"])
            if conn.entries:
                entry = conn.entries[0]
                return {
                    attr.key: attr.value
                    for attr in entry
                    if attr.value is not None
                }
        except LDAPException as exc:
            logger.debug("LDAP: could not read attrs for %s: %s", user_dn, exc)
        return {}

    def _map_attrs(self, raw: dict) -> dict:
        """Map raw LDAP attributes to internal fields per attribute_map."""
        mapped = {}
        for ldap_attr, internal in self.config.attribute_map.items():
            value = raw.get(ldap_attr)
            if isinstance(value, list):
                value = value[0] if value else None
            if value is not None:
                mapped[internal] = str(value)
        return mapped
