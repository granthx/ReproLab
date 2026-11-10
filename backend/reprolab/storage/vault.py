"""Content-Addressed Artifact Vault for ReproLab (Milestone 1).

Provides:
- Cryptographic SHA-256 content addressing
- 2-level directory sharding ({sha256[:2]}/{sha256[2:4]}/{sha256})
- Path traversal defense and hex validation
- Read-only file permission lockdown
- Read-time and write-time integrity verification
"""

import hashlib
from pathlib import Path
import re
import stat
from typing import Tuple


SHA256_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class VaultError(Exception):
    """Base exception for artifact vault errors."""
    pass


class VaultSecurityError(VaultError):
    """Raised when an illegal path or invalid hash is supplied."""
    pass


class VaultIntegrityError(VaultError):
    """Raised when file content does not match its expected SHA-256 hash."""
    pass


class ContentAddressedVault:
    """Hardened local content-addressed storage engine."""

    def __init__(self, vault_root: Path):
        self.root = vault_root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _validate_hash(self, sha256_hash: str) -> str:
        """Ensure hash is strictly a 64-character hex string with no traversal tokens."""
        if not isinstance(sha256_hash, str):
            raise VaultSecurityError(f"Expected string hash, got {type(sha256_hash)}")
        
        cleaned = sha256_hash.strip().lower()
        if "/" in cleaned or "\\" in cleaned or ".." in cleaned or not SHA256_HEX_PATTERN.match(cleaned):
            raise VaultSecurityError(f"Invalid SHA-256 hash or path traversal detected: {sha256_hash}")
        
        return cleaned

    def _get_shard_path(self, sha256_hash: str, extension: str = "") -> Path:
        """Compute the sharded filesystem path: root/aa/bb/aabb...ext."""
        valid_hash = self._validate_hash(sha256_hash)
        shard1 = valid_hash[:2]
        shard2 = valid_hash[2:4]
        filename = f"{valid_hash}{extension}"
        target_dir = self.root / shard1 / shard2
        return target_dir / filename

    def store_bytes(self, data: bytes, extension: str = "") -> Tuple[str, Path]:
        """Store raw bytes content-addressed by its SHA-256 digest.
        
        Returns:
            Tuple of (sha256_hex_hash, absolute_file_path)
        """
        if not isinstance(data, (bytes, bytearray)):
            raise VaultError(f"Expected bytes, got {type(data)}")

        sha256_hash = hashlib.sha256(data).hexdigest()
        clean_ext = f".{extension.lstrip('.')}" if extension else ""
        target_path = self._get_shard_path(sha256_hash, clean_ext)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        if not target_path.exists():
            # Write data atomically
            temp_path = target_path.with_suffix(f"{clean_ext}.tmp")
            temp_path.write_bytes(data)

            # Verification prior to final commit
            written_hash = hashlib.sha256(temp_path.read_bytes()).hexdigest()
            if written_hash != sha256_hash:
                temp_path.unlink(missing_ok=True)
                raise VaultIntegrityError("Write verification failed: hash mismatch during storage.")

            # Make read-only (0o444)
            try:
                temp_path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            except Exception:
                pass  # Best effort on Windows

            temp_path.replace(target_path)

        return sha256_hash, target_path

    def get_path(self, sha256_hash: str) -> Path:
        """Locate the path for a given SHA-256 hash."""
        valid_hash = self._validate_hash(sha256_hash)
        shard1 = valid_hash[:2]
        shard2 = valid_hash[2:4]
        target_dir = self.root / shard1 / shard2

        if not target_dir.exists():
            raise FileNotFoundError(f"Artifact {valid_hash} not found in vault.")

        # Match either exact hash or hash with extension
        for candidate in target_dir.iterdir():
            if candidate.name.startswith(valid_hash):
                return candidate

        raise FileNotFoundError(f"Artifact {valid_hash} not found in vault.")

    def get_bytes(self, sha256_hash: str) -> bytes:
        """Retrieve bytes and verify SHA-256 integrity on read."""
        target_path = self.get_path(sha256_hash)
        data = target_path.read_bytes()

        # Enforce read-time verification
        actual_hash = hashlib.sha256(data).hexdigest()
        if actual_hash != self._validate_hash(sha256_hash):
            raise VaultIntegrityError(
                f"Tampering detected! Stored file {target_path} has hash {actual_hash}, expected {sha256_hash}"
            )

        return data

    def verify_integrity(self, sha256_hash: str) -> bool:
        """Check whether the stored file matches its hash without throwing."""
        try:
            self.get_bytes(sha256_hash)
            return True
        except (VaultIntegrityError, FileNotFoundError, VaultSecurityError):
            return False

