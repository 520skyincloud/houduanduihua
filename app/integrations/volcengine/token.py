from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from typing import Dict


VERSION = "001"
APP_ID_LENGTH = 24

PRIVILEGES = {
    "publish_stream": 0,
    "publish_audio_stream": 1,
    "publish_video_stream": 2,
    "publish_data_stream": 3,
    "subscribe_stream": 4,
}


def _put_bytes(buffer: bytearray, value: bytes) -> None:
    buffer.extend(struct.pack("<H", len(value)))
    buffer.extend(value)


def _put_string(buffer: bytearray, value: str) -> None:
    _put_bytes(buffer, value.encode("utf-8"))


def _put_tree_map_uint32(buffer: bytearray, values: Dict[int, int]) -> None:
    buffer.extend(struct.pack("<H", len(values)))
    for key, value in values.items():
        buffer.extend(struct.pack("<H", key))
        buffer.extend(struct.pack("<I", value))


def generate_rtc_token(
    app_id: str,
    app_key: str,
    room_id: str,
    user_id: str,
    expire_seconds: int,
) -> str:
    now = int(time.time())
    expire_at = now + expire_seconds
    nonce = int.from_bytes(os.urandom(4), "little")

    privileges = {
        PRIVILEGES["publish_stream"]: 0,
        PRIVILEGES["publish_audio_stream"]: 0,
        PRIVILEGES["publish_video_stream"]: 0,
        PRIVILEGES["publish_data_stream"]: 0,
        PRIVILEGES["subscribe_stream"]: 0,
    }

    message = bytearray()
    message.extend(struct.pack("<I", nonce))
    message.extend(struct.pack("<I", now))
    message.extend(struct.pack("<I", expire_at))
    _put_string(message, room_id)
    _put_string(message, user_id)
    _put_tree_map_uint32(message, privileges)

    signature = hmac.new(
        app_key.encode("utf-8"),
        bytes(message),
        hashlib.sha256,
    ).digest()

    content = bytearray()
    _put_bytes(content, bytes(message))
    _put_bytes(content, signature)
    return VERSION + app_id[:APP_ID_LENGTH] + base64.b64encode(bytes(content)).decode("utf-8")
