"""API keys: stored as salted SHA-256 hashes with the account and plan they belong to. A key is
shown once when it is issued and never stored in the clear."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path

from ..platform.grounding import Account


class Keys:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.rows: dict[str, dict[str, str]] = json.loads(path.read_text()) if path.exists() else {}

    @staticmethod
    def _hash(key: str, salt: str) -> str:
        return hashlib.sha256((salt + key).encode()).hexdigest()

    def issue(self, account_id: str, plan: str) -> str:
        key = "dgp_" + secrets.token_urlsafe(24)
        salt = secrets.token_hex(8)
        self.rows[key[:12]] = {"account_id": account_id, "plan": plan, "salt": salt, "hash": self._hash(key, salt)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.rows, indent=1))
        return key

    def account(self, key: str | None) -> Account | None:
        if not key:
            return None
        row = self.rows.get(key[:12])
        if row is None or not hmac.compare_digest(row["hash"], self._hash(key, row["salt"])):
            return None
        return Account(row["account_id"], row["plan"])
