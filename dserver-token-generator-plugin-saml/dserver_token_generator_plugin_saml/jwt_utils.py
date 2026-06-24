"""Pure helpers: attribute mapping + dserver JWT minting. No pysaml2 import, so unit-testable
standalone."""
import datetime

import jwt


def map_identity(identity, attribute_map, username_field):
    """Map a pysaml2 ``get_identity()`` dict to internal fields and pick the username.

    :param identity: ``{saml_attribute_name: [values]}`` from the SAML assertion
    :param attribute_map: ``{saml_attribute_name: internal_field}``
    :param username_field: which internal field is the username (e.g. ``user_id``)
    :returns: ``(username_or_None, fields_dict)``
    """
    fields = {}
    for saml_attr, values in (identity or {}).items():
        field = attribute_map.get(saml_attr)
        if not field:
            continue
        if isinstance(values, (list, tuple)):
            value = values[0] if values else None
        else:
            value = values
        if value is not None:
            fields[field] = value
    return fields.get(username_field), fields


def mint_token(private_key_file, algorithm, username, expiry_hours=24,
               name=None, email=None, extra=None):
    """Mint a dserver-compatible RS256 JWT signed with dserver's private key."""
    with open(private_key_file, "r") as f:
        private_key = f.read()

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "username": username,
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(hours=expiry_hours),
        "provider": "saml",
    }
    if name:
        payload["name"] = name
    if email:
        payload["email"] = email
    if extra:
        payload.update(extra)

    return jwt.encode(payload, private_key, algorithm=algorithm)
