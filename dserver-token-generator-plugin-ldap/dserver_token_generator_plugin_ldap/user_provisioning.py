"""
User provisioning for LDAP-authenticated users.

LDAP performs *authentication* (proving who the user is); dserver's own SQL
user table performs *authorization* (which base URIs the user may search /
register on). An authenticated user whose name is not in dserver's table gets
401 on every route, so on first successful login we (optionally) create the
user and grant permissions on the configured base URIs.

All DB access goes through the public helpers in ``dservercore.utils`` and runs
inside the request's app context.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class UserProvisioner:
    """Create + grant permissions for LDAP-authenticated users in dserver."""

    def __init__(
        self,
        auto_provision: bool = True,
        default_base_uris: Optional[list] = None,
        grant_register: bool = True,
    ):
        self.auto_provision = auto_provision
        self.default_base_uris = default_base_uris or []
        self.grant_register = grant_register

    def provision_user(
        self,
        username: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> None:
        """Ensure the user exists in dserver and has the configured permissions."""
        if not self.auto_provision:
            return

        from dservercore.utils import (
            user_exists,
            register_user,
            base_uri_exists,
            get_permission_info,
            register_permissions,
        )

        # Create the user if missing. Do NOT re-register an existing user (that
        # would clobber their is_admin flag); only optionally refresh the
        # display_name for an existing entry.
        if not user_exists(username):
            register_user(username, {"is_admin": False, "display_name": display_name})
            logger.info("LDAP: provisioned new dserver user %s", username)
        elif display_name:
            self._update_display_name(username, display_name)

        # Grant permissions on the configured base URIs (idempotent).
        for base_uri in self.default_base_uris:
            if not base_uri_exists(base_uri):
                logger.warning(
                    "LDAP: base URI %s not registered; cannot grant %s",
                    base_uri, username,
                )
                continue
            permissions = get_permission_info(base_uri)
            changed = False
            if username not in permissions.get("users_with_search_permissions", []):
                permissions.setdefault("users_with_search_permissions", []).append(username)
                changed = True
            if self.grant_register and username not in permissions.get(
                "users_with_register_permissions", []
            ):
                permissions.setdefault("users_with_register_permissions", []).append(username)
                changed = True
            if changed:
                register_permissions(base_uri, permissions)
                logger.info("LDAP: granted %s permissions on %s", username, base_uri)

    @staticmethod
    def _update_display_name(username: str, display_name: str) -> None:
        """Set display_name on an existing user if it is currently empty."""
        try:
            from dservercore.sql_models import User
            from dservercore import sql_db

            user = User.query.filter_by(username=username).first()
            if user and not user.display_name:
                user.display_name = display_name
                sql_db.session.commit()
                logger.info("LDAP: updated display_name for %s", username)
        except Exception as exc:  # pragma: no cover - never block login on this
            logger.warning("LDAP: could not update display_name for %s: %s",
                           username, exc)
