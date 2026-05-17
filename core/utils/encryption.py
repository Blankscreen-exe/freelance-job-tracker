from django.conf import settings
from django.db import models


def _fernet():
    from cryptography.fernet import Fernet
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class EncryptedTextField(models.TextField):
    """
    Transparently encrypts the field value using Fernet (AES-128-CBC + HMAC)
    before writing to the database and decrypts after reading.

    Stores as TEXT (Fernet tokens are ~2× the plaintext length in base64).
    Reports itself as TextField in migrations so switching from CharField
    to this field only requires an AlterField migration, not a new field type.
    """

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except Exception:
            # Return ciphertext as-is if decryption fails (e.g., migrating old plaintext rows).
            return value

    def get_prep_value(self, value):
        if not value:
            return value
        raw = super().get_prep_value(value)
        # Already encrypted (Fernet tokens start with 'gAAAAA').
        if isinstance(raw, str) and raw.startswith('gAAAAA'):
            return raw
        return _fernet().encrypt(raw.encode()).decode()

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Pretend to be a plain TextField so no custom-field migration is generated.
        path = 'django.db.models.TextField'
        return name, path, args, kwargs
