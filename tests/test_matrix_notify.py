from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

SPEC = importlib.util.spec_from_file_location(
    "matrix_notify", Path(__file__).resolve().parents[1] / "matrix-notify/scripts/matrix_notify.py")
notify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notify)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def test_env_is_literal_and_process_values_override_hermes_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("export MATRIX_HOMESERVER=https://matrix.example.org\n"
                            "MATRIX_USER_ID=@bot:example.org\nMATRIX_HOME_ROOM='!room:example.org'\n"
                            "MATRIX_PASSWORD='$(touch sentinel) `command` $HOME'\n")
            with patch.dict(os.environ, {"MATRIX_ROOM_ID": "!override:example.org"}, clear=True):
                values = notify.settings(str(path))
            self.assertEqual(values["MATRIX_ROOM_ID"], "!override:example.org")
            self.assertEqual(values["MATRIX_PASSWORD"], "$(touch sentinel) `command` $HOME")

    def test_rejects_unsafe_urls_and_invalid_boolean(self):
        base = {"MATRIX_HOMESERVER": "https://matrix.example.org", "MATRIX_USER_ID": "@bot:example.org",
                "MATRIX_ROOM_ID": "!room:example.org", "XDG_CONFIG_HOME": self.temporary.name}
        for url in ("http://matrix.example.org", "https://user:password@matrix.example.org", "https://matrix.example.org/?token=secret"):
            with self.subTest(url=url), patch.dict(os.environ, {**base, "MATRIX_HOMESERVER": url}, clear=True):
                with self.assertRaises(notify.NotifyError):
                    notify.settings()
        with patch.dict(os.environ, {**base, "MATRIX_ALLOW_HTTP": "maybe", "MATRIX_HOMESERVER": "http://matrix.example.org"}, clear=True):
            with self.assertRaisesRegex(notify.NotifyError, "must be true or false"):
                notify.settings()

    def test_env_parse_errors_do_not_disclose_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("TOKEN='super-private\n")
            with self.assertRaises(notify.NotifyError) as error:
                notify.dotenv(path)
            self.assertNotIn("super-private", str(error.exception))

    def test_threads_and_unicode_are_preserved_and_oversized_messages_rejected(self):
        content = notify.message("Done ✓\nhttps://host.example.org/report/", "$root")
        self.assertEqual(content["body"], "Done ✓\nhttps://host.example.org/report/")
        self.assertEqual(content["m.relates_to"]["event_id"], "$root")
        with self.assertRaisesRegex(notify.NotifyError, "HTML"):
            notify.message("✓" * 4001)
        with self.assertRaisesRegex(notify.NotifyError, "empty"):
            notify.message(" \n")

    def test_device_store_excludes_concurrent_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            with notify.device_lock(path):
                with self.assertRaisesRegex(notify.NotifyError, "Another Matrix notification"):
                    with notify.device_lock(path):
                        self.fail("lock should be exclusive")


class DeliveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.nio = types.ModuleType("nio")
        for name in ("LoginResponse", "SyncResponse", "RoomGetStateEventResponse",
                     "RoomGetStateEventError", "RoomSendResponse", "KeysUploadResponse"):
            setattr(self.nio, name, type(name, (), {}))
        self.client = Mock()
        self.client.rooms = {"!room:example.org": types.SimpleNamespace(encrypted=True)}
        self.client.olm = object()
        self.client.should_upload_keys = True
        self.client.sync = AsyncMock(return_value=self.nio.SyncResponse())
        self.encryption = self.nio.RoomGetStateEventResponse()
        self.encryption.content = {"algorithm": "m.megolm.v1.aes-sha2"}
        self.client.room_get_state_event = AsyncMock(return_value=self.encryption)
        self.client.keys_upload = AsyncMock(return_value=self.nio.KeysUploadResponse())
        sent = self.nio.RoomSendResponse()
        sent.event_id = "$delivered"
        self.client.room_send = AsyncMock(return_value=sent)
        self.client.close = AsyncMock()
        self.nio.AsyncClient = Mock(return_value=self.client)
        self.nio.AsyncClientConfig = Mock()
        aiohttp = types.ModuleType("aiohttp")
        aiohttp.TraceConfig = Mock(return_value=types.SimpleNamespace(on_request_redirect=[]))
        aiohttp.ClientSession = Mock()
        modules = patch.dict("sys.modules", {"nio": self.nio, "aiohttp": aiohttp})
        modules.start()
        self.addCleanup(modules.stop)
        self.values = {"MATRIX_HOMESERVER": "https://matrix.example.org", "MATRIX_USER_ID": "@bot:example.org",
                       "MATRIX_ROOM_ID": "!room:example.org", "MATRIX_THREAD_ID": ""}
        (self.directory / "session.json").write_text(json.dumps({
            "homeserver": self.values["MATRIX_HOMESERVER"], "user_id": self.values["MATRIX_USER_ID"],
            "device_id": "DEDICATED", "access_token": "test-session-token"}))
        (self.directory / "store").mkdir()
        (self.directory / "store/device.db").touch()

    async def test_send_restores_session_and_passes_stable_transaction_and_thread(self):
        result = await notify.run(self.values, self.directory, "send", notify.message("Done", "$root"), "stable-id")
        self.assertEqual(result["event_id"], "$delivered")
        self.assertTrue(result["encrypted"])
        self.client.restore_login.assert_called_once_with("@bot:example.org", "DEDICATED", "test-session-token")
        self.client.login.assert_not_called()
        self.client.room_send.assert_awaited_once()
        self.assertEqual(self.client.room_send.call_args.kwargs["tx_id"], "stable-id")
        self.assertEqual(self.client.room_send.call_args.args[2]["m.relates_to"]["event_id"], "$root")
        self.client.close.assert_awaited_once()

    async def test_check_posts_no_message_and_init_is_idempotent(self):
        for operation in ("check", "init"):
            result = await notify.run(self.values, self.directory, operation)
            self.assertEqual(result["status"], "ready")
        self.client.room_send.assert_not_called()
        self.client.login.assert_not_called()

    async def test_new_device_does_not_reuse_imported_hermes_device(self):
        (self.directory / "session.json").unlink()
        self.values.update(MATRIX_PASSWORD="test-password", MATRIX_DEVICE_ID="HERMES", MATRIX_ACCESS_TOKEN="hermes-token")
        login = self.nio.LoginResponse()
        login.user_id, login.device_id, login.access_token = "@bot:example.org", "NEW_DEVICE", "new-token"
        self.client.login = AsyncMock(return_value=login)
        await notify.run(self.values, self.directory, "init")
        self.assertEqual(self.nio.AsyncClient.call_args.kwargs["device_id"], "")
        self.client.restore_login.assert_not_called()
        session = json.loads((self.directory / "session.json").read_text())
        self.assertEqual(session["device_id"], "NEW_DEVICE")
        self.assertEqual((self.directory / "session.json").stat().st_mode & 0o777, 0o600)

    async def test_missing_store_cannot_replace_existing_device_keys(self):
        (self.directory / "store/device.db").unlink()
        with self.assertRaisesRegex(notify.NotifyError, "store is missing"):
            await notify.run(self.values, self.directory, "send", notify.message("Done"), "id")
        self.nio.AsyncClient.assert_not_called()

    async def test_encryption_state_failure_never_sends_plaintext(self):
        self.client.rooms["!room:example.org"].encrypted = False
        with self.assertRaisesRegex(notify.NotifyError, "inconsistent"):
            await notify.run(self.values, self.directory, "send", notify.message("Private"), "id")
        self.client.room_send.assert_not_called()
        self.client.close.assert_awaited_once()

    async def test_failed_sync_does_not_leak_server_error_or_send(self):
        self.client.sync.return_value = types.SimpleNamespace(status_code="M_UNKNOWN_TOKEN", message="test-secret")
        with self.assertRaises(notify.NotifyError) as error:
            await notify.run(self.values, self.directory, "send", notify.message("Private"), "id")
        self.assertNotIn("test-secret", str(error.exception))
        self.client.room_send.assert_not_called()

    async def test_membership_and_server_errors_block_delivery(self):
        self.client.rooms = {}
        with self.assertRaisesRegex(notify.NotifyError, "has not joined"):
            await notify.run(self.values, self.directory, "send", notify.message("Private"), "id")
        self.client.room_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
