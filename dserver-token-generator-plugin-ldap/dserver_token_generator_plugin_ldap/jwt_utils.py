"""
JWT token generation utilities.

This module handles JWT token creation and signing for authenticated users.
Copied from dserver-token-generator-plugin-oauth2 so LDAP-minted tokens are
byte-for-byte compatible with what dserver verifies.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt

from .config import JwtConfig

logger = logging.getLogger(__name__)


class JwtTokenGenerator:
    """Generate and sign JWT tokens for authenticated users."""

    def __init__(self, config: JwtConfig):
        """
        Initialize the JWT token generator.

        Args:
            config: JWT configuration object
        """
        self.config = config
        self._private_key: Optional[str] = None
        self._public_key: Optional[str] = None

    @property
    def private_key(self) -> str:
        """Load and cache the private key."""
        if self._private_key is None:
            self._private_key = self._load_key(self.config.private_key_file)
        return self._private_key

    @property
    def public_key(self) -> str:
        """Load and cache the public key."""
        if self._public_key is None:
            self._public_key = self._load_key(self.config.public_key_file)
        return self._public_key

    @staticmethod
    def _load_key(path: str) -> str:
        """Load a key from file."""
        key_path = Path(path)
        if not key_path.exists():
            raise FileNotFoundError(f"Key file not found: {path}")
        return key_path.read_text()

    def generate_token(
        self,
        username: str,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
        permissions: Optional[list] = None,
        additional_claims: Optional[dict] = None,
    ) -> str:
        """
        Generate a JWT token for an authenticated user.

        Args:
            username: Unique username
            email: User's email address
            display_name: User's display name
            permissions: List of permissions/roles
            additional_claims: Any additional claims to include

        Returns:
            Signed JWT token string
        """
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(hours=self.config.token_expiry_hours)

        payload = {
            # Standard JWT claims
            "iss": self.config.issuer,
            "aud": self.config.audience,
            "sub": username,
            "iat": now,
            "exp": expiry,
            "nbf": now,

            # Custom claims for dserver
            "username": username,
        }

        # Add optional claims
        if email:
            payload["email"] = email

        if display_name:
            payload["name"] = display_name

        if permissions:
            payload["permissions"] = permissions

        # Add any additional claims
        if additional_claims:
            payload.update(additional_claims)

        # Sign the token
        token = jwt.encode(
            payload,
            self.private_key,
            algorithm=self.config.algorithm
        )

        logger.info(f"Generated JWT token for user: {username}")
        return token

    def verify_token(self, token: str) -> Optional[dict]:
        """
        Verify and decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.config.algorithm],
                audience=self.config.audience,
                issuer=self.config.issuer,
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
        return None
