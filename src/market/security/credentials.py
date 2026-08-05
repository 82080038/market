"""Credential encryption at rest using Fernet (pustaka/33).

Provides:
- Symmetric encryption for sensitive data (API keys, broker credentials)
- Key rotation support
- Encrypted credential store with .env integration
- Secure key generation and management
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CredentialEntry:
    """A stored encrypted credential."""

    key: str
    encrypted_value: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    rotated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CredentialManager:
    """Manages encryption and storage of credentials at rest.

    Uses Fernet (AES-128-CBC + HMAC-SHA256) for symmetric encryption.
    Falls back to base64 encoding if cryptography library is not installed
    (with a loud warning — this is NOT secure).
    """

    def __init__(self, master_key: str | bytes | None = None) -> None:
        self._fernet: Any = None
        self._store: dict[str, CredentialEntry] = {}
        self._key_history: list[bytes] = []

        if master_key:
            self._init_fernet(master_key)
        else:
            # Try to load from environment
            env_key = os.environ.get("CREDENTIAL_MASTER_KEY")
            if env_key:
                self._init_fernet(env_key)
            else:
                logger.warning(
                    "No master key provided. Generating ephemeral key. "
                    "Credentials will NOT persist across restarts.",
                )
                self._generate_key()

    def _generate_key(self) -> None:
        """Generate a new Fernet key."""
        try:
            from cryptography.fernet import Fernet  # type: ignore[import-not-found,unused-ignore]

            key = Fernet.generate_key()
            self._init_fernet(key)
        except ImportError:
            logger.error(
                "cryptography library not installed. "
                "Credentials will be base64-encoded (NOT secure).",
            )

    def _init_fernet(self, key: str | bytes) -> None:
        """Initialize Fernet with the given key."""
        try:
            from cryptography.fernet import Fernet

            key_bytes = key.encode() if isinstance(key, str) else key

            # Validate key format
            try:
                self._fernet = Fernet(key_bytes)
            except Exception:
                # Try deriving a valid Fernet key from the input
                derived = base64.urlsafe_b64encode(
                    hashlib.sha256(key_bytes).digest(),
                )
                self._fernet = Fernet(derived)
                key_bytes = derived

            self._key_history.append(key_bytes)
        except ImportError:
            logger.error(
                "cryptography library not installed. "
                "Credentials will be base64-encoded (NOT secure).",
            )

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string.

        Args:
            plaintext: String to encrypt.

        Returns:
            Encrypted string (base64-encoded).
        """
        if self._fernet is not None:
            return str(self._fernet.encrypt(plaintext.encode()).decode())
        # Fallback: base64 (NOT secure)
        return base64.b64encode(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt an encrypted string.

        Args:
            ciphertext: Encrypted string.

        Returns:
            Decrypted plaintext string.
        """
        if self._fernet is not None:
            # Try current key first, then historical keys
            for key in self._key_history:
                try:
                    from cryptography.fernet import Fernet

                    f = Fernet(key)
                    return str(f.decrypt(ciphertext.encode()).decode())
                except Exception:
                    continue
            raise ValueError("Failed to decrypt — no valid key found")
        # Fallback: base64
        return base64.b64decode(ciphertext.encode()).decode()

    def store(self, key: str, value: str, metadata: dict[str, Any] | None = None) -> None:
        """Store an encrypted credential.

        Args:
            key: Credential identifier (e.g., "broker_api_key").
            value: Plaintext value to encrypt and store.
            metadata: Optional metadata.
        """
        encrypted = self.encrypt(value)
        self._store[key] = CredentialEntry(
            key=key,
            encrypted_value=encrypted,
            metadata=metadata or {},
        )

    def retrieve(self, key: str) -> str | None:
        """Retrieve and decrypt a credential.

        Args:
            key: Credential identifier.

        Returns:
            Decrypted plaintext value, or None if not found.
        """
        entry = self._store.get(key)
        if entry is None:
            return None
        return self.decrypt(entry.encrypted_value)

    def rotate_key(self, new_key: str | bytes | None = None) -> None:
        """Rotate the encryption key. Re-encrypts all stored credentials.

        Args:
            new_key: New master key. If None, generates a new one.
        """
        # Decrypt all with old key
        plaintexts: dict[str, str] = {}
        for k, entry in self._store.items():
            plaintexts[k] = self.decrypt(entry.encrypted_value)

        # Initialize new key
        if new_key:
            self._init_fernet(new_key)
        else:
            self._generate_key()

        # Re-encrypt all with new key
        for k, v in plaintexts.items():
            entry = self._store[k]
            entry.encrypted_value = self.encrypt(v)
            entry.rotated_at = datetime.now(UTC).isoformat()

        logger.info(f"Rotated encryption key, re-encrypted {len(plaintexts)} credentials")

    def load_from_env(self, prefix: str = "CRED_") -> int:
        """Load credentials from environment variables.

        Args:
            prefix: Environment variable prefix to look for.

        Returns:
            Number of credentials loaded.
        """
        count = 0
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                cred_key = env_key[len(prefix):].lower()
                self.store(cred_key, env_value)
                count += 1
        return count

    def save_to_file(self, path: Path | str) -> None:
        """Save encrypted credentials to a JSON file.

        Args:
            path: File path to save to.
        """
        import json

        data = {
            k: {
                "key": v.key,
                "encrypted_value": v.encrypted_value,
                "created_at": v.created_at,
                "rotated_at": v.rotated_at,
                "metadata": v.metadata,
            }
            for k, v in self._store.items()
        }
        Path(path).write_text(json.dumps(data, indent=2))

    def load_from_file(self, path: Path | str) -> int:
        """Load encrypted credentials from a JSON file.

        Args:
            path: File path to load from.

        Returns:
            Number of credentials loaded.
        """
        import json

        p = Path(path)
        if not p.exists():
            return 0

        data = json.loads(p.read_text())
        for k, v in data.items():
            self._store[k] = CredentialEntry(
                key=v["key"],
                encrypted_value=v["encrypted_value"],
                created_at=v["created_at"],
                rotated_at=v.get("rotated_at"),
                metadata=v.get("metadata", {}),
            )
        return len(self._store)

    @property
    def keys(self) -> list[str]:
        """List of stored credential keys."""
        return list(self._store.keys())

    @property
    def count(self) -> int:
        """Number of stored credentials."""
        return len(self._store)
