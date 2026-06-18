"""Default provider: embed no S3 credentials (user supplies their own keys)."""

from . import CredentialProvider, Credentials


class NoneProvider(CredentialProvider):
    def issue(self, username: str, context: dict) -> Credentials:
        return Credentials()
