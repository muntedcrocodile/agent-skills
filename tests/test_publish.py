from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publisher", ROOT / "tailscale-share/scripts/publish.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

FAKE_TAILSCALE = '''#!/usr/bin/env python3
import json, os, pathlib, sys
state_path = pathlib.Path(os.environ["SHARE_TEST_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
state["calls"].append(args)
if args == ["status", "--json"]:
    print(json.dumps(state["identity"]))
elif args == ["serve", "status", "--json"]:
    print(json.dumps(state["config"]))
elif args[:1] in (["serve"], ["funnel"]):
    port = next(a.split("=", 1)[1] for a in args if a.startswith("--https="))
    key = "test.example.ts.net:" + port
    config = state["config"]
    if args[-1] == "off":
        config.get("TCP", {}).pop(port, None)
        config.get("Web", {}).pop(key, None)
        config.get("AllowFunnel", {}).pop(key, None)
    else:
        config.setdefault("TCP", {})[port] = {"HTTPS": True}
        config.setdefault("Web", {})[key] = {"Handlers": {"/": {"Path": args[-1]}}}
        config.setdefault("AllowFunnel", {})[key] = args[0] == "funnel"
else:
    sys.exit("Unexpected arguments: " + repr(args))
state_path.write_text(json.dumps(state))
'''


class PublishingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        fake = self.bin / "tailscale"
        fake.write_text(FAKE_TAILSCALE)
        fake.chmod(0o755)
        self.state_file = self.base / "state.json"
        self.old_route = {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5733"}}}
        self.state_file.write_text(json.dumps({
            "identity": {"BackendState": "Running", "Self": {"DNSName": "test.example.ts.net."}, "CurrentTailnet": {"Name": "example.test"}},
            "config": {"TCP": {"443": {"HTTPS": True}}, "Web": {"test.example.ts.net:443": self.old_route}},
            "calls": [],
        }))
        environment = {"PATH": str(self.bin) + ":" + os.environ["PATH"], "SHARE_TEST_STATE": str(self.state_file), "TAILSCALE_SHARE_ROOT": str(self.base / "shares"), "TAILSCALE_SHARE_TAILNET": "example.test", "AGENT_SKILLS_CONFIG": str(self.base / "preferences.json")}
        self.environment = patch.dict(os.environ, environment)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.source = self.base / "report with spaces.html"
        self.source.write_text("<!doctype html><title>A report</title><h1>Report</h1>")

    def state(self) -> dict:
        return json.loads(self.state_file.read_text())

    def mutate(self, change) -> None:
        state = self.state()
        change(state)
        self.state_file.write_text(json.dumps(state))

    def test_private_publish_preserves_other_routes_and_encodes_filename(self) -> None:
        url = publisher.publish(self.source, "report")
        self.assertEqual(url, "https://test.example.ts.net:8444/report/report%20with%20spaces.html")
        self.assertEqual((self.base / "shares/tailnet/report" / self.source.name).read_text(), self.source.read_text())
        state = self.state()
        self.assertEqual(state["config"]["Web"]["test.example.ts.net:443"], self.old_route)
        self.assertFalse(any(call[0] == "funnel" for call in state["calls"]))
        self.assertFalse((self.base / "shares/public").exists())

    def test_public_site_is_separate_and_preserves_assets(self) -> None:
        publisher.publish(self.source, "private-report")
        site = self.base / "site"
        site.mkdir()
        (site / "index.html").write_text('<img src="assets/plot.svg">')
        (site / "assets").mkdir()
        (site / "assets/plot.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        url = publisher.publish(site, "public-plan", public=True)
        self.assertEqual(url, "https://test.example.ts.net:8443/public-plan/")
        self.assertTrue((self.base / "shares/public/public-plan/assets/plot.svg").is_file())
        self.assertFalse((self.base / "shares/public/private-report").exists())
        allowed = self.state()["config"]["AllowFunnel"]
        self.assertFalse(allowed["test.example.ts.net:8444"])
        self.assertTrue(allowed["test.example.ts.net:8443"])

    def test_existing_private_endpoint_is_idempotent(self) -> None:
        publisher.ensure_endpoint()
        publisher.ensure_endpoint()
        changes = [call for call in self.state()["calls"] if "--bg" in call]
        self.assertEqual(len(changes), 1)

    def test_conflicting_route_is_not_overwritten(self) -> None:
        self.mutate(lambda state: state["config"]["TCP"].update({"8444": {"TCPForward": "127.0.0.1:8080"}}))
        with self.assertRaisesRegex(RuntimeError, "already used"):
            publisher.publish(self.source, "report")
        self.assertFalse(any("--bg" in call for call in self.state()["calls"]))

    def test_private_endpoint_with_funnel_enabled_is_rejected(self) -> None:
        self.mutate(lambda state: state["config"].update({"AllowFunnel": {"test.example.ts.net:8444": True}}))
        with self.assertRaisesRegex(RuntimeError, "Funnel enabled"):
            publisher.publish(self.source, "report")

    def test_symlink_and_dotfiles_are_rejected(self) -> None:
        site = self.base / "site"
        site.mkdir()
        (site / "leak").symlink_to(self.source)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            publisher.publish(site, "report")
        (site / "leak").unlink()
        (site / ".env").write_text("not-a-real-secret")
        with self.assertRaisesRegex(RuntimeError, "hidden"):
            publisher.publish(site, "report")
        self.assertEqual(self.state()["calls"], [])

    def test_wrong_tailnet_and_disconnected_host_are_rejected(self) -> None:
        self.mutate(lambda state: state["identity"]["CurrentTailnet"].update({"Name": "other"}))
        with self.assertRaisesRegex(RuntimeError, "Expected tailnet"):
            publisher.ensure_endpoint()
        self.mutate(lambda state: state["identity"].update({"BackendState": "NeedsLogin"}))
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            publisher.ensure_endpoint()

    def test_existing_publication_is_retained(self) -> None:
        publisher.publish(self.source, "report")
        self.source.write_text("changed")
        with self.assertRaisesRegex(RuntimeError, "already exists"):
            publisher.publish(self.source, "report")
        self.assertIn("A report", (self.base / "shares/tailnet/report" / self.source.name).read_text())

    def test_stop_only_removes_selected_endpoint_and_retains_files(self) -> None:
        publisher.publish(self.source, "private")
        publisher.publish(self.source, "public", public=True)
        publisher.stop(public=True)
        state = self.state()
        self.assertNotIn("8443", state["config"]["TCP"])
        self.assertIn("8444", state["config"]["TCP"])
        self.assertIn("443", state["config"]["TCP"])
        self.assertTrue((self.base / "shares/public/public" / self.source.name).is_file())
        self.assertFalse(any("reset" in call for call in state["calls"]))

    def test_path_traversal_slug_is_rejected_without_mutation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Name must"):
            publisher.publish(self.source, "../outside")
        self.assertEqual(self.state()["calls"], [])

    def test_filesystem_permission_retry_elevates_only_the_tailscale_command(self) -> None:
        denied = subprocess.CompletedProcess([], 1, stdout="", stderr="401 Unauthorized: must be root")
        accepted = subprocess.CompletedProcess([], 0, stdout="configured", stderr="")
        with patch.object(publisher.subprocess, "run", side_effect=[denied, accepted]) as run:
            self.assertEqual(publisher.tailscale("serve", "--bg", "--https=8444", "/tmp/artifacts"), "configured")
        self.assertEqual(run.call_args_list[1].args[0], ["sudo", "-n", "tailscale", "serve", "--bg", "--https=8444", "/tmp/artifacts"])

    def test_read_only_permission_failure_does_not_elevate(self) -> None:
        denied = subprocess.CompletedProcess([], 1, stdout="", stderr="401 Unauthorized: must be root")
        with patch.object(publisher.subprocess, "run", return_value=denied) as run:
            with self.assertRaisesRegex(RuntimeError, "Unauthorized"):
                publisher.tailscale("serve", "status", "--json")
            self.assertEqual(run.call_count, 1)

    def test_personal_preferences_are_local_and_environment_overrides_them(self) -> None:
        path = self.base / "preferences.json"
        path.write_text(json.dumps({"tailscale-share": {"tailnet": "other.example", "root": str(self.base / "configured")}}))
        self.assertEqual(publisher.identity(), "test.example.ts.net")
        self.assertEqual(publisher.share_root(), self.base / "shares")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TAILSCALE_SHARE_TAILNET")
            os.environ.pop("TAILSCALE_SHARE_ROOT")
            with self.assertRaisesRegex(RuntimeError, "Expected tailnet"):
                publisher.identity()
            self.assertEqual(publisher.share_root(), self.base / "configured")


if __name__ == "__main__":
    unittest.main()
