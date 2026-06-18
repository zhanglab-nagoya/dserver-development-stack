"""
MinIO credential provider (OPTIONAL, isolated).

The only module coupled to MinIO. ``minio`` is imported lazily inside methods so
that importing the plugin (or any other provider) never requires it; install it
via the ``[minio]`` extra. To drop MinIO support entirely, delete this file and
its single entry in ``credentials/__init__._PROVIDER_MODULES``.

On each request it mints a fresh MinIO **service account** scoped by an inline
policy to the user's dataset prefix (``u/<username>/``). Service accounts (rather
than overwriting a user's secret) mean previously downloaded configs keep working
until they expire — MinIO only returns a secret at creation, so re-minting is
inherent.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from . import CredentialProvider, Credentials

logger = logging.getLogger(__name__)


def _default_policy(bucket: str, prefix: str) -> dict:
    arn = f"arn:aws:s3:::{bucket}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                "Resource": [f"{arn}/{prefix}*"],
            },
            {
                # s3:prefix condition is only valid for ListBucket.
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": [arn],
                "Condition": {"StringLike": {"s3:prefix": [f"{prefix}*"]}},
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetBucketLocation"],
                "Resource": [arn],
            },
        ],
    }


def _policy_for(bucket: str, prefix: str) -> dict:
    template_path = os.environ.get("CONFIG_GENERATOR_MINIO_POLICY_TEMPLATE", "")
    if template_path:
        with open(template_path) as f:
            raw = f.read()
        return json.loads(raw.replace("{bucket}", bucket).replace("{prefix}", prefix))
    return _default_policy(bucket, prefix)


class MinioServiceAccountProvider(CredentialProvider):
    def issue(self, username: str, context: dict) -> Credentials:
        # Lazy import: keeps `minio` out of the import path unless this provider runs.
        from minio import MinioAdmin
        from minio.credentials import StaticProvider as MinioStaticProvider

        endpoint = os.environ.get("CONFIG_GENERATOR_MINIO_ADMIN_ENDPOINT", "minio:9000")
        access = os.environ.get("CONFIG_GENERATOR_MINIO_ADMIN_ACCESS_KEY", "minioadmin")
        secret = os.environ.get("CONFIG_GENERATOR_MINIO_ADMIN_SECRET_KEY", "minioadmin")
        secure = os.environ.get("CONFIG_GENERATOR_MINIO_SECURE", "false").lower() == "true"

        bucket = context["bucket"]
        prefix = context["prefix"]
        policy = _policy_for(bucket, prefix)

        # The minio SDK expects expiration as an RFC3339 *string*, not a datetime.
        expiration = None
        expiry_seconds = os.environ.get("CONFIG_GENERATOR_MINIO_SVCACCT_EXPIRY_SECONDS", "")
        if expiry_seconds:
            exp_dt = datetime.now(timezone.utc) + timedelta(seconds=int(expiry_seconds))
            expiration = exp_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        admin = MinioAdmin(
            endpoint=endpoint,
            credentials=MinioStaticProvider(access, secret),
            secure=secure,
        )

        kwargs = {"name": username[:64], "policy": policy}
        if expiration is not None:
            kwargs["expiration"] = expiration
        result = admin.add_service_account(**kwargs)

        access_key, secret_key = _parse_service_account(result)
        if not access_key or not secret_key:
            raise RuntimeError(
                f"MinIO add_service_account returned no usable credentials: {result!r}"
            )
        logger.info("Minted MinIO service account %s for user %s", access_key, username)
        return Credentials(access_key=access_key, secret_key=secret_key)


def _parse_service_account(result) -> tuple:
    """Extract (access_key, secret_key) from add_service_account's response.

    Tolerates the differing shapes across minio SDK versions (JSON string or
    dict; camelCase or snake_case; optionally nested under 'credentials').
    """
    data = result
    if isinstance(result, (str, bytes)):
        try:
            data = json.loads(result)
        except (ValueError, TypeError):
            return None, None
    if not isinstance(data, dict):
        return None, None
    creds = data.get("credentials", data)
    access = creds.get("accessKey") or creds.get("access_key")
    secret = creds.get("secretKey") or creds.get("secret_key")
    return access, secret
