"""管理面板的认证与凭据存储。

密码用 PBKDF2-HMAC-SHA256 加盐哈希后写到数据目录，令牌是无状态 HMAC 签名
的，因此重启服务不会让已登录的会话失效，也不需要额外的会话存储。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

from .dirs import get_data_dir
from .log import logger

PBKDF2_ITERATIONS = 240_000
HASH_NAME = "sha256"
TOKEN_TTL_SECONDS = 7 * 24 * 3600
MIN_PASSWORD_LENGTH = 8

ADMIN_FILE_NAME = "admin.json"


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _admin_file() -> Path:
    return get_data_dir() / ADMIN_FILE_NAME


def _hash_password(password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return _b64encode(salt), _b64encode(digest)


def _verify_password(password: str, salt_b64: str, hash_b64: str) -> bool:
    salt = _b64decode(salt_b64)
    expected = _b64decode(hash_b64)
    digest = hashlib.pbkdf2_hmac(
        HASH_NAME, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(digest, expected)


class AdminAuth:
    """管理凭据与令牌的读写。"""

    def __init__(self) -> None:
        self._state: Optional[dict[str, Any]] = None

    def _load(self) -> dict[str, Any]:
        if self._state is not None:
            return self._state
        path = _admin_file()
        if path.is_file():
            try:
                self._state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                logger.warning(f"Failed to read admin credentials: {e}")
                self._state = {}
        else:
            self._state = {}
        return self._state

    def _save(self, state: dict[str, Any]) -> None:
        path = _admin_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        self._state = state

    def reload(self) -> None:
        """丢弃内存缓存，下次访问时重新读取文件。"""
        self._state = None

    @property
    def initialized(self) -> bool:
        return bool(self._load().get("password_hash"))

    def setup(self, password: str) -> None:
        """首次设置管理员密码。"""
        if self.initialized:
            raise ValueError("管理员密码已设置")
        salt_b64, hash_b64 = _hash_password(password)
        secret = _b64encode(secrets.token_bytes(32))
        self._save(
            {
                "password_salt": salt_b64,
                "password_hash": hash_b64,
                "token_secret": secret,
                "created_at": int(time.time()),
            }
        )

    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.verify_password(old_password):
            raise ValueError("原密码不正确")
        salt_b64, hash_b64 = _hash_password(new_password)
        state = dict(self._load())
        state["password_salt"] = salt_b64
        state["password_hash"] = hash_b64
        # 换密码即让旧令牌失效
        state["token_secret"] = _b64encode(secrets.token_bytes(32))
        state["updated_at"] = int(time.time())
        self._save(state)

    def verify_password(self, password: str) -> bool:
        state = self._load()
        if not state.get("password_hash"):
            return False
        return _verify_password(
            password, state["password_salt"], state["password_hash"]
        )

    @property
    def _secret(self) -> bytes:
        secret = self._load().get("token_secret")
        if not secret:
            raise ValueError("管理员密码尚未设置")
        return _b64decode(secret)

    def create_token(self, ttl: int = TOKEN_TTL_SECONDS) -> str:
        payload = {"exp": int(time.time()) + ttl, "nonce": secrets.token_hex(8)}
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._secret, raw, hashlib.sha256).digest()
        return f"{_b64encode(raw)}.{_b64encode(signature)}"

    def verify_token(self, token: str) -> bool:
        """校验令牌签名与有效期。"""
        if not token or "." not in token:
            return False
        raw_b64, sig_b64 = token.split(".", 1)
        try:
            raw = _b64decode(raw_b64)
            signature = _b64decode(sig_b64)
        except (ValueError, base64.binascii.Error):
            return False
        expected = hmac.new(self._secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return False
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError:
            return False
        return int(payload.get("exp", 0)) > int(time.time())


admin_auth = AdminAuth()
