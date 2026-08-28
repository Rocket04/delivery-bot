"""Авторизация Telegram Mini App: initData (WebAppData) — HMAC-SHA256 от бот-токена.

Алгоритм (доки Telegram): initData — query-строка с параметрами, включая hash.
1) auth_date не старше max_age_seconds; 2) все пары key=value КРОМЕ hash отсортировать
по ключу и склеить "key=value\n..."; 3) secret_key = HMAC_SHA256(msg=bot_token,
key="WebAppData"); 4) hash должен совпасть с HMAC_SHA256(msg=собранная_строка,
key=secret_key).

Секретов в коде нет: bot_token приходит от вызывающего (get_settings().bot_token).
Защита: compare_digest — без утечки по времени.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

MAX_AGE_SECONDS_DEFAULT = 86_400  # сутки, как в WebAppData


def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def verify_init_data(
    init_data: str, bot_token: str, max_age_seconds: int = MAX_AGE_SECONDS_DEFAULT
) -> dict | None:
    """Проверяет подпись initData и возраст auth_date.

    Возвращает распарсенный объект user ({"id": ..., "first_name": ..., ...})
    из параметра user, либо None при неверной подписи/просрочке/плохом формате.
    """
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except (TypeError, ValueError):
        return None
    if auth_date <= 0 or time.time() - auth_date > max_age_seconds:
        return None

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = _hmac_sha256(b"WebAppData", bot_token.encode())
    expected = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        user = json.loads(pairs.get("user", "null"))
    except json.JSONDecodeError:
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user