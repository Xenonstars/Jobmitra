"""
Secrets manager — stores credentials in OS-native keyring instead of .env.
Fallback: encrypted local file if keyring is unavailable.
Supports LinkedIn session cookies and Naukri credentials.
"""

import json
import os
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)

SERVICE_NAME = "job-automation-app"

# Fallback: encrypted file under user home
_FALLBACK_DIR = os.path.join(os.path.expanduser("~"), ".job-automation")
_FALLBACK_PATH = os.path.join(_FALLBACK_DIR, "credentials.enc")

_has_keyring = False
try:
    import keyring
    # Verify keyring works (some CI environments have the package but no backend)
    try:
        keyring.get_password(SERVICE_NAME, "__test__")
        _has_keyring = True
    except Exception:
        _has_keyring = False
except ImportError:
    pass


def _get_fallback(service: str, key: str) -> Optional[str]:
    """Read a credential from the encrypted fallback file."""
    try:
        if not os.path.exists(_FALLBACK_PATH):
            return None
        from cryptography.fernet import Fernet
        key_path = os.path.join(_FALLBACK_DIR, ".key")
        if not os.path.exists(key_path):
            return None
        with open(key_path, "rb") as f:
            cipher = Fernet(f.read())
        with open(_FALLBACK_PATH, "rb") as f:
            data = json.loads(cipher.decrypt(f.read()).decode())
        entry = data.get(service, {}).get(key)
        return entry
    except Exception as e:
        logger.debug("fallback_read_failed", error=str(e))
        return None


def _set_fallback(service: str, key: str, value: str) -> None:
    """Store a credential in the encrypted fallback file."""
    try:
        from cryptography.fernet import Fernet
        os.makedirs(_FALLBACK_DIR, exist_ok=True)
        key_path = os.path.join(_FALLBACK_DIR, ".key")
        if not os.path.exists(key_path):
            import base64
            from cryptography.fernet import Fernet
            crypto_key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(crypto_key)
        with open(key_path, "rb") as f:
            cipher = Fernet(f.read())
        if os.path.exists(_FALLBACK_PATH):
            with open(_FALLBACK_PATH, "rb") as f:
                data = json.loads(cipher.decrypt(f.read()).decode())
        else:
            data = {}
        data.setdefault(service, {})[key] = value
        with open(_FALLBACK_PATH, "wb") as f:
            f.write(cipher.encrypt(json.dumps(data).encode()))
    except Exception as e:
        logger.warning("fallback_write_failed", error=str(e))


def get_credential(key: str) -> Optional[str]:
    """
    Retrieve a credential. Tries OS keyring first, falls back to encrypted file.

    Available keys:
        linkedin_email, linkedin_password,
        naukri_username, naukri_password,
        anthropic_api_key
    """
    if _has_keyring:
        try:
            val = keyring.get_password(SERVICE_NAME, key)
            if val:
                return val
        except Exception:
            pass
    return _get_fallback(SERVICE_NAME, key)


def set_credential(key: str, value: str) -> None:
    """
    Store a credential in the OS keyring (with encrypted file fallback).

    Available keys:
        linkedin_email, linkedin_password,
        naukri_username, naukri_password,
        anthropic_api_key
    """
    if _has_keyring:
        try:
            keyring.set_password(SERVICE_NAME, key, value)
            return
        except Exception:
            pass
    _set_fallback(SERVICE_NAME, key, value)


def delete_credential(key: str) -> None:
    """Remove a stored credential."""
    if _has_keyring:
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except Exception:
            pass
    try:
        path = _FALLBACK_PATH
        if os.path.exists(path):
            from cryptography.fernet import Fernet
            key_path = os.path.join(_FALLBACK_DIR, ".key")
            if os.path.exists(key_path):
                with open(key_path, "rb") as f:
                    cipher = Fernet(f.read())
                with open(path, "rb") as f:
                    data = json.loads(cipher.decrypt(f.read()).decode())
                data.get(SERVICE_NAME, {}).pop(key, None)
                with open(path, "wb") as f:
                    f.write(cipher.encrypt(json.dumps(data).encode()))
    except Exception as e:
        logger.debug("fallback_delete_failed", error=str(e))
