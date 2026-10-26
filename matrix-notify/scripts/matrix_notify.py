#!/usr/bin/env python3
"""Send one Matrix notification using a persistent, encryption-capable device."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urlsplit
import uuid


class NotifyError(Exception):
    pass


def dotenv(path: Path) -> dict[str, str]:
    """Read literal KEY=value assignments; never execute or interpolate them."""
    result = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key.strip()):
            raise NotifyError(f"Invalid env assignment at line {number}; values suppressed")
        try:
            parts = shlex.split(raw, comments=True)
        except ValueError:
            raise NotifyError(f"Invalid env quoting at line {number}; values suppressed") from None
        if len(parts) > 1:
            raise NotifyError(f"Quote env values containing spaces at line {number}")
        result[key.strip()] = parts[0] if parts else ""
    return result


def settings(env_file: str | None = None) -> dict[str, str]:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    selected = env_file or os.environ.get("MATRIX_NOTIFY_ENV_FILE")
    path = Path(selected).expanduser() if selected else config_home / "agent-skills/matrix.env"
    if selected and not path.is_file():
        raise NotifyError("Selected Matrix env file is missing")
    values = dotenv(path) if path.is_file() else {}
    values.update({key: value for key, value in os.environ.items() if key.startswith("MATRIX_")})
    # Accept existing Hermes destination names without importing its device keys.
    values["MATRIX_ROOM_ID"] = values.get("MATRIX_ROOM_ID") or values.get("MATRIX_HOME_ROOM", "")
    values["MATRIX_THREAD_ID"] = values.get("MATRIX_THREAD_ID") or values.get("MATRIX_HOME_ROOM_THREAD_ID", "")
    for key in ("MATRIX_HOMESERVER", "MATRIX_USER_ID", "MATRIX_ROOM_ID"):
        if not values.get(key):
            raise NotifyError(f"Configure {key} in the Matrix env file")
    parsed = urlsplit(values["MATRIX_HOMESERVER"])
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise NotifyError("MATRIX_HOMESERVER must be an HTTP(S) base URL without credentials, query, or fragment")
    if parsed.scheme == "http" and not enabled(values, "MATRIX_ALLOW_HTTP", False):
        raise NotifyError("Use HTTPS, or explicitly set MATRIX_ALLOW_HTTP=true for a trusted transport")
    if not values["MATRIX_ROOM_ID"].startswith("!"):
        raise NotifyError("MATRIX_ROOM_ID must be a room ID beginning with !")
    if values["MATRIX_THREAD_ID"] and not values["MATRIX_THREAD_ID"].startswith("$"):
        raise NotifyError("MATRIX_THREAD_ID must be an event ID beginning with $")
    enabled(values, "MATRIX_ALLOW_UNVERIFIED_DEVICES", True)
    values["MATRIX_HOMESERVER"] = values["MATRIX_HOMESERVER"].rstrip("/")
    return values


def enabled(values: dict[str, str], key: str, default: bool) -> bool:
    value = values.get(key, str(default)).lower()
    if value not in ("true", "false"):
        raise NotifyError(f"{key} must be true or false")
    return value == "true"


def state_directory(values: dict[str, str]) -> Path:
    data = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
    return Path(values.get("MATRIX_NOTIFY_STATE_DIR", str(data / "agent-skills/matrix-notify"))).expanduser().resolve()


@contextmanager
def device_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    with (directory / "device.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise NotifyError("Another Matrix notification is using this device; retry when it finishes") from None
        yield


def message(body: str, thread: str = "") -> dict:
    if not body.strip():
        raise NotifyError("Message is empty")
    if len(body.encode("utf-8")) > 12000:
        raise NotifyError("Message is too long; publish the breakdown as HTML on the tailnet and send its link")
    content = {"msgtype": "m.text", "body": body}
    if thread:
        content["m.relates_to"] = {"rel_type": "m.thread", "event_id": thread,
                                  "is_falling_back": True, "m.in_reply_to": {"event_id": thread}}
    return content


def require_response(response, expected, operation: str):
    if not isinstance(response, expected):
        code = getattr(response, "status_code", "")
        safe_code = code if isinstance(code, str) and re.fullmatch(r"M_[A-Z_]+", code) else "request failed"
        raise NotifyError(f"Matrix {operation}: {safe_code}; server details suppressed")
    return response


async def run(values: dict[str, str], directory: Path, operation: str,
              content: dict | None = None, transaction_id: str | None = None) -> dict:
    # Import here so configuration checks and unit tests need no third-party packages.
    from nio import (AsyncClient, AsyncClientConfig, LoginResponse, SyncResponse,
                     RoomGetStateEventResponse, RoomGetStateEventError, RoomSendResponse)
    from aiohttp import ClientSession, TraceConfig

    session_file = directory / "session.json"
    session = json.loads(session_file.read_text()) if session_file.is_file() else None
    if session and (session["homeserver"] != values["MATRIX_HOMESERVER"] or session["user_id"] != values["MATRIX_USER_ID"]):
        raise NotifyError("Matrix account changed; select a different MATRIX_NOTIFY_STATE_DIR")
    if not session and operation != "init":
        raise NotifyError("No notification device yet; run notify.sh init once")
    if not session and not values.get("MATRIX_PASSWORD"):
        raise NotifyError("Set MATRIX_PASSWORD privately for the initial dedicated device login")
    store = directory / "store"
    store.mkdir(mode=0o700, exist_ok=True)
    if session and not any(store.glob("*.db")):
        raise NotifyError("Notification encryption store is missing; preserve it with its session, or initialize a new state directory")
    client = AsyncClient(values["MATRIX_HOMESERVER"], values["MATRIX_USER_ID"],
                         device_id=session["device_id"] if session else "", store_path=str(store),
                         config=AsyncClientConfig(encryption_enabled=True, store_sync_tokens=True,
                                                  max_limit_exceeded=1, max_timeouts=1, request_timeout=20))
    async def refuse_redirect(*_):
        raise NotifyError("Homeserver redirected the request; configure its canonical URL")

    trace = TraceConfig()
    trace.on_request_redirect.append(refuse_redirect)
    client.client_session = ClientSession(trace_configs=[trace])
    try:
        if session:
            client.restore_login(session["user_id"], session["device_id"], session["access_token"])
        else:
            response = require_response(await client.login(values["MATRIX_PASSWORD"], device_name="Agent Matrix notifications"), LoginResponse, "login")
            session = {"homeserver": values["MATRIX_HOMESERVER"], "user_id": response.user_id,
                       "device_id": response.device_id, "access_token": response.access_token}
            temporary = session_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(session) + "\n")
            temporary.chmod(0o600)
            temporary.replace(session_file)
        room_id = values["MATRIX_ROOM_ID"]
        require_response(await client.sync(timeout=0, full_state=True, sync_filter={
            "presence": {"types": []}, "room": {"rooms": [room_id], "timeline": {"limit": 0}}}), SyncResponse, "sync")
        if room_id not in client.rooms:
            raise NotifyError("The notification account has not joined the configured room")
        encryption = await client.room_get_state_event(room_id, "m.room.encryption")
        if isinstance(encryption, RoomGetStateEventResponse):
            if encryption.content.get("algorithm") != "m.megolm.v1.aes-sha2" or not client.rooms[room_id].encrypted or not client.olm:
                raise NotifyError("Room encryption state is unsupported or inconsistent; no message sent")
            encrypted = True
        elif isinstance(encryption, RoomGetStateEventError) and encryption.status_code == "M_NOT_FOUND":
            if client.rooms[room_id].encrypted:
                raise NotifyError("Room encryption state is inconsistent; no message sent")
            encrypted = False
        else:
            require_response(encryption, RoomGetStateEventResponse, "encryption check")
        if operation != "send":
            return {"status": "ready", "encrypted": encrypted, "device_id": session["device_id"]}
        if client.should_upload_keys:
            from nio import KeysUploadResponse
            require_response(await client.keys_upload(), KeysUploadResponse, "key upload")
        response = require_response(await client.room_send(
            room_id, "m.room.message", content, tx_id=transaction_id,
            ignore_unverified_devices=enabled(values, "MATRIX_ALLOW_UNVERIFIED_DEVICES", True)), RoomSendResponse, "send")
        if not isinstance(response.event_id, str) or not response.event_id.startswith("$"):
            raise NotifyError("Matrix send returned no valid event ID")
        return {"status": "sent", "event_id": response.event_id, "encrypted": encrypted,
                "transaction_id": transaction_id}
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="Explicit private env file (never sourced)")
    parser.add_argument("operation", choices=("init", "check", "send"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--message", help="Short message; stdin avoids shell quoting for arbitrary content")
    source.add_argument("--file", help="UTF-8 message file, or - for stdin")
    parser.add_argument("--transaction-id", help="Reuse this ID only when retrying the same delivery")
    args = parser.parse_args()
    os.umask(0o077)
    logging.disable(logging.CRITICAL)  # nio debug/errors can include private events or credentials.
    transaction = None
    try:
        values = settings(args.env_file)
        content = None
        if args.operation == "send":
            body = args.message
            if args.file:
                body = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
            if body is None:
                raise NotifyError("Supply --message or --file (use --file - for stdin)")
            content = message(body, values["MATRIX_THREAD_ID"])
            transaction = args.transaction_id or "notify-" + uuid.uuid4().hex
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", transaction):
                raise NotifyError("Transaction ID must contain 1–128 letters, digits, underscores, or hyphens")
        directory = state_directory(values)
        with device_lock(directory):
            result = asyncio.run(asyncio.wait_for(run(values, directory, args.operation, content, transaction), timeout=90))
        print(json.dumps(result))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        detail = str(error) if isinstance(error, NotifyError) else f"{type(error).__name__}; private details suppressed"
        print(f"Matrix notification failed: {detail}", file=sys.stderr)
        if transaction:
            print(f"Delivery may be uncertain. Retry the same message with --transaction-id {transaction}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
