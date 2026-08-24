"""ORION Secure Secret Store — Windows Credential Manager and .env fallback.

Provides a unified interface for storing and retrieving API secrets used by
ORION providers (Polymarket, Coinbase, etc.) using the most secure available
mechanism on Windows, with .env fallback when secure store is unavailable.

Design principles:
1. Never store secrets in plaintext in the database, logs, or git.
2. Never transmit secrets over APIs or via GET endpoints.
3. Fallback chain: Windows Credential Manager → .env (never committed).
4. All secret retrieval goes through this module only; the frontend never sees
   raw secrets — only "CONFIGURED" or a fingerprint.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("orion.secretstore")


@dataclass
class SecretStoreResult:
    """Result of a secret store operation."""

    success: bool
    value: str | None = None  # partial fingerprint, never full secret
    error: str | None = None

    def __bool__(self) -> bool:
        return self.success


class SecretType:
    """Typed secret categories for proper handling."""

    GAMMA_API_KEY = "gamma_api_key"  # noqa: S105
    CLOB_TOKEN = "clob_token"  # noqa: S105
    WS_TOKEN = "ws_token"  # noqa: S105
    FARO_API_KEY = "faro_api_key"  # noqa: S105
    OPENAI_API_KEY = "openai_api_key"  # noqa: S105
    GENERIC = "generic"  # noqa: S105


class SecretStoreABC(ABC):
    """Abstract base for secret storage implementations."""

    @abstractmethod
    def store_secret(
        self, secret_type: str, value: str, metadata: dict[str, Any] | None = None
    ) -> SecretStoreResult:
        """Store a secret. Returns result with success flag and partial fingerprint."""
        pass

    @abstractmethod
    def retrieve_secret(self, secret_type: str) -> SecretStoreResult:
        """Retrieve a secret. Returns result with success flag.
        The full secret value is never returned to callers that shouldn't have it.
        """
        pass

    @abstractmethod
    def clear_secret(self, secret_name: str) -> SecretStoreResult:
        """Clear a stored secret."""
        pass

    @abstractmethod
    def status(self) -> dict[str, bool]:
        """Return status dict: configured, authenticated, ws_connected, etc."""
        pass

    @abstractmethod
    def get_raw_secret(self, secret_type: str) -> str | None:
        """Return the actual secret value for outbound calls (never via API).

        This is distinct from `retrieve_secret`, which only ever returns a
        masked fingerprint for status displays. Only server-side outbound
        clients (e.g. a provider sending an authenticated request) may call
        this — it must never be wired to an HTTP response.
        """
        pass


class WindowsCredentialStore(SecretStoreABC):
    """Windows Credential Manager wrapper.

    Uses the wincred library to store secrets in the user's credential vault.
    Only available on Windows. Falls back gracefully if wincred is not installed.
    """

    def __init__(self) -> None:
        self._available = False
        self._cred = None
        try:
            import wincred  # type: ignore[import]
            self._cred = wincred
            self._available = True
        except ImportError:
            logger.debug("wincred not available, Windows Credential Manager disabled")

    def _cred_key(self, secret_type: str) -> str:
        """Generate a credential key for the given secret type."""
        return f"orion_{secret_type}"

    def store_secret(
        self, secret_type: str, value: str, metadata: dict[str, Any] | None = None
    ) -> SecretStoreResult:
        if not self._available:
            err = "Windows Credential Manager not available"
            return SecretStoreResult(success=False, error=err)
        try:
            key = self._cred_key(secret_type)
            self._cred.set_key_credential(target=key, username="ORION", password=value)
            # Return fingerprint (first 4 + last 4 chars)
            if len(value) >= 8:
                fingerprint = f"{value[:4]}****{value[-4:]}"
            else:
                fingerprint = f"****{value}****"
            logger.info(f"Stored secret via Windows Credential Manager: {secret_type}")
            return SecretStoreResult(success=True, value=fingerprint)
        except Exception as e:
            logger.error(f"Failed to store secret via Windows Credential Manager: {e}")
            return SecretStoreResult(success=False, error=str(e))

    def retrieve_secret(self, secret_type: str) -> SecretStoreResult:
        if not self._available:
            err = "Windows Credential Manager not available"
            return SecretStoreResult(success=False, error=err)
        try:
            key = self._cred_key(secret_type)
            cred = self._cred.get_key_credential(target=key, username="ORION")
            if cred:
                value = cred.password
                if len(value) >= 8:
                    fingerprint = f"{value[:4]}****{value[-4:]}"
                else:
                    fingerprint = f"****{value}****"
                return SecretStoreResult(success=True, value=fingerprint)
            return SecretStoreResult(success=False, error="Secret not found in credential manager")
        except Exception as e:
            logger.error(f"Failed to retrieve secret: {e}")
            return SecretStoreResult(success=False, error=str(e))

    def clear_secret(self, secret_name: str) -> SecretStoreResult:
        if not self._available:
            err = "Windows Credential Manager not available"
            return SecretStoreResult(success=False, error=err)
        try:
            key = self._cred_key(secret_name)
            self._cred.delete_key_credential(target=key)
            logger.info(f"Cleared secret via Windows Credential Manager: {secret_name}")
            return SecretStoreResult(success=True)
        except Exception as e:
            logger.error(f"Failed to clear secret: {e}")
            return SecretStoreResult(success=False, error=str(e))

    def status(self) -> dict[str, bool]:
        if not self._available:
            return {"configured": False, "authenticated": False}
        try:
            key = self._cred_key("gamma_api_key")
            cred = self._cred.get_key_credential(target=key, username="ORION")
            return {"configured": cred is not None, "authenticated": cred is not None}
        except Exception:
            return {"configured": False, "authenticated": False}

    def get_raw_secret(self, secret_type: str) -> str | None:
        if not self._available:
            return None
        try:
            key = self._cred_key(secret_type)
            cred = self._cred.get_key_credential(target=key, username="ORION")
            return cred.password if cred else None
        except Exception as e:
            logger.error(f"Failed to retrieve raw secret via Windows Credential Manager: {e}")
            return None


class EnvFallbackSecretStore(SecretStoreABC):
    """ .env fallback secret store.

    Only used when Windows secure stores are unavailable.
    .env file MUST be in .gitignore and must NOT contain real secrets in git.
    This class reads from os.environ only — no file writing.
    """

    def store_secret(
        self, secret_type: str, value: str, metadata: dict[str, Any] | None = None
    ) -> SecretStoreResult:
        # .env fallback: set the env var in the current process only
        # Never write to .env file from the app
        env_name = f"ORION_{secret_type.upper()}"
        os.environ[env_name] = value
        fingerprint = f"{value[:4]}****{value[-4:]}" if len(value) >= 8 else f"****{value}****"
        logger.warning(f"Stored secret via .env FALLBACK: {secret_type} (env var: {env_name})")
        return SecretStoreResult(success=True, value=fingerprint)

    def retrieve_secret(self, secret_type: str) -> SecretStoreResult:
        env_name = f"ORION_{secret_type.upper()}"
        value = os.environ.get(env_name)
        if value:
            fingerprint = f"{value[:4]}****{value[-4:]}" if len(value) >= 8 else f"****{value}****"
            return SecretStoreResult(success=True, value=fingerprint)
        return SecretStoreResult(success=False, error=f"Secret {secret_type} not in environment")

    def clear_secret(self, secret_name: str) -> SecretStoreResult:
        env_name = f"ORION_{secret_name.upper()}"
        if env_name in os.environ:
            del os.environ[env_name]
            logger.info(f"Cleared env var: {env_name}")
        return SecretStoreResult(success=True)

    def status(self) -> dict[str, bool]:
        # Check if any ORION secrets are configured
        for st in ["gamma_api_key", "clob_token"]:
            if self.retrieve_secret(st).success:
                return {"configured": True, "authenticated": True}
        return {"configured": False, "authenticated": False}

    def get_raw_secret(self, secret_type: str) -> str | None:
        env_name = f"ORION_{secret_type.upper()}"
        return os.environ.get(env_name)


class SecretStoreFactory:
    """Factory to create the best available secret store in priority order."""

    @staticmethod
    def create() -> SecretStoreABC:
        """Create the best available secret store in priority order."""
        # 1. Try Windows Credential Manager — select it whenever the library
        # itself is available, not only when a secret happens to already be
        # stored there (checking "already configured" made it impossible to
        # ever bootstrap the first secret into this store).
        store = WindowsCredentialStore()
        if store._available:
            logger.info("Using Windows Credential Manager for secret store")
            return store

        # 2. Fallback to .env (environment variables only, never write to file)
        # NOTE: this store only lives in process memory (os.environ) — a
        # secret saved here does NOT survive an API restart unless the
        # `wincred` package is installed so the branch above can be used.
        logger.warning("No Windows Credential Manager available, using .env fallback "
                       "(secret will not survive an API restart)")
        return EnvFallbackSecretStore()


# Convenience function
def get_secret_store() -> SecretStoreABC:
    """Get the configured secret store instance."""
    return SecretStoreFactory.create()