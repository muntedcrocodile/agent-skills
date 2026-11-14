from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "journal/scripts/journal.py"
spec = importlib.util.spec_from_file_location("journal", SCRIPT)
journal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(journal)


class JournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "demo"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, inside: Path | None = None) -> str:
        """Run from the project root, or from a nested directory to check root discovery."""
        location = inside or self.project
        return subprocess.run([sys.executable, str(SCRIPT), "--project", str(location), *arguments],
                              capture_output=True, text=True, check=True).stdout

    def entries(self) -> list[dict]:
        return json.loads((self.project / ".agent-journal/journal.json").read_text())["entries"]

    def test_open_items_are_not_added_again(self) -> None:
        self.run_cli("add", "--key", "Bad Thing", "--title", "A bad thing")
        self.run_cli("set", "bad-thing", "IGNORED")
        output = self.run_cli("add", "--key", "other", "--title", "a BAD thing!")
        self.assertIn("not added again", output)
        self.assertEqual([(e["key"], e["status"]) for e in self.entries()], [("bad-thing", "IGNORED")])

    def test_done_item_reoccurs_in_active_section(self) -> None:
        self.run_cli("add", "--key", "leak", "--title", "Leak")
        self.run_cli("set", "leak", "DONE")
        page = (self.project / ".agent-journal/index.html").read_text()
        self.assertIn("Nothing open.", page.split("<details>")[0])
        self.assertIn("[DONE]", page.split("<details>")[1])
        self.assertNotIn("[DONE]", page.split("<details>")[2])
        self.assertIn("reoccured", self.run_cli("add", "--key", "leak", "--title", "Leak"))
        entry = self.entries()[0]
        self.assertEqual((entry["status"], entry["occurrences"]), ("REOCCURED", 2))
        page = (self.project / ".agent-journal/index.html").read_text()
        active, done, _ = page.split("<details>")
        self.assertIn("[REOCCURED]", active)
        self.assertIn("No completed items.", done)
        self.assertNotIn("<details open", page)

    def test_ignored_items_are_collapsed_and_not_readded(self) -> None:
        self.run_cli("add", "--key", "noise", "--title", "Noise")
        self.run_cli("set", "noise", "IGNORED")
        self.assertIn("not added again", self.run_cli("add", "--key", "noise", "--title", "Noise"))
        self.assertEqual(self.run_cli("list").strip(), "(no entries)")
        active, done, ignored = (self.project / ".agent-journal/index.html").read_text().split("<details>")
        self.assertIn("Nothing open.", active)
        self.assertIn("Ignored (1)", ignored)
        self.assertIn("[IGNORED]", ignored)

    def test_active_order_escaping_and_git_exclude(self) -> None:
        (self.project / "sub").mkdir()
        self.run_cli("add", "--key", "a", "--title", "<script>x</script> {{done}}", inside=self.project / "sub")
        self.run_cli("add", "--key", "b", "--title", "Doing", "--status", "DOING", "--tag", "Idea", "--tag", "ux")
        page = (self.project / ".agent-journal/index.html").read_text()
        self.assertLess(page.index("[DOING]"), page.index("[TODO]"))
        self.assertIn("&lt;script&gt;x&lt;/script&gt; {{done}}", page)
        self.assertNotIn("<script>x", page)
        self.assertIn('<span class="tag">idea</span>', page)
        self.assertIn("Doing #idea #ux", self.run_cli("list"))
        self.run_cli("add", "--key", "c", "--title", "Third")
        exclude = (self.project / ".git/info/exclude").read_text().splitlines()
        self.assertEqual(exclude.count("/.agent-journal/"), 1)

    def test_unknown_key_fails(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.project), "set", "nope", "DONE"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
