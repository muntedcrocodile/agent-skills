#!/usr/bin/env python3
"""Keep a per-project journal of tracked items with statuses and render it as HTML."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys

STATUSES = ("TODO", "DOING", "DONE", "IGNORED", "REOCCURED")
ACTIVE_ORDER = {"REOCCURED": 0, "DOING": 1, "TODO": 2}
COLLAPSED = ("DONE", "IGNORED")
DIRECTORY = ".agent-journal"
TEMPLATE = Path(__file__).resolve().parents[1] / "assets/journal.html"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def git(project: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(["git", "-C", str(project), *arguments], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip()


def project_root(start: Path) -> Path:
    top = git(start, "rev-parse", "--show-toplevel")
    return Path(top) if top else start.resolve()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:64] or "item"


class Journal:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.directory = project / DIRECTORY
        self.data_path = self.directory / "journal.json"
        self.html_path = self.directory / "index.html"
        if self.data_path.is_file():
            self.data = json.loads(self.data_path.read_text())
        else:
            self.data = {"project": project.name, "entries": []}

    @property
    def entries(self) -> list[dict]:
        return self.data["entries"]

    def find(self, key: str, title: str | None = None) -> dict | None:
        key = slug(key)
        wanted = slug(title) if title else None
        for entry in self.entries:
            if entry["key"] == key or (wanted and slug(entry["title"]) == wanted):
                return entry
        return None

    def record(self, entry: dict, status: str, note: str | None) -> None:
        entry["status"] = status
        entry["updated"] = now()
        entry.setdefault("history", []).append({"at": entry["updated"], "status": status, **({"note": note} if note else {})})

    def add(self, key: str, title: str, detail: str = "", where: str = "", status: str = "TODO",
            note: str | None = None, tags: list[str] | None = None) -> str:
        existing = self.find(key, title)
        if existing is None:
            entry = {"key": slug(key), "title": title, "detail": detail, "where": where,
                     "tags": [slug(tag) for tag in tags or []], "created": now(), "occurrences": 1}
            self.entries.append(entry)
            self.record(entry, status, note)
            return f"added {entry['key']} [{status}]"
        if existing["status"] != "DONE":
            return f"exists {existing['key']} [{existing['status']}]; not added again"
        existing["occurrences"] = existing.get("occurrences", 1) + 1
        if detail:
            existing["detail"] = detail
        if where:
            existing["where"] = where
        self.record(existing, "REOCCURED", note or "Encountered again after being marked DONE")
        return f"reoccured {existing['key']} [REOCCURED]"

    def set(self, key: str, status: str, note: str | None = None) -> str:
        entry = self.find(key)
        if entry is None:
            raise SystemExit(f"No journal entry with key {slug(key)!r}; run list to see keys.")
        self.record(entry, status, note)
        return f"set {entry['key']} [{status}]"

    def save(self) -> None:
        self.directory.mkdir(exist_ok=True)
        exclude = git(self.project, "rev-parse", "--git-path", "info/exclude")
        if exclude:
            path = Path(exclude) if os.path.isabs(exclude) else self.project / exclude
            lines = path.read_text().splitlines() if path.is_file() else []
            if f"/{DIRECTORY}/" not in lines:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join([*lines, f"/{DIRECTORY}/"]) + "\n")
        self.data_path.write_text(json.dumps(self.data, indent=2) + "\n")
        self.render()

    def render(self) -> Path:
        # Group by status priority; newest first within each status.
        newest = sorted(self.entries, key=lambda e: e["updated"], reverse=True)
        active = sorted((e for e in newest if e["status"] not in COLLAPSED), key=lambda e: ACTIVE_ORDER.get(e["status"], 9))
        done = [e for e in newest if e["status"] == "DONE"]
        ignored = [e for e in newest if e["status"] == "IGNORED"]
        counts = " ".join(
            f'<span class="badge s-{s.lower()}">{s} {sum(e["status"] == s for e in self.entries)}</span>'
            for s in STATUSES if any(e["status"] == s for e in self.entries))
        values = {
            "project": html.escape(self.data.get("project", self.project.name)),
            "updated": html.escape(now()),
            "counts": counts or '<span class="badge">empty</span>',
            "active": "\n".join(map(card, active)) or '<p class="empty">Nothing open.</p>',
            "done_count": str(len(done)),
            "done": "\n".join(map(card, done)) or '<p class="empty">No completed items.</p>',
            "ignored_count": str(len(ignored)),
            "ignored": "\n".join(map(card, ignored)) or '<p class="empty">No ignored items.</p>',
        }
        # One pass, so text inside entries can never be treated as a placeholder.
        page = re.sub(r"\{\{(\w+)\}\}", lambda match: values[match.group(1)], TEMPLATE.read_text())
        self.directory.mkdir(exist_ok=True)
        self.html_path.write_text(page)
        return self.html_path


def card(entry: dict) -> str:
    status = entry["status"]
    escape = html.escape
    parts = [f'<article class="item s-{status.lower()}">',
             f'<header><span class="badge s-{status.lower()}">[{status}]</span> <h3>{escape(entry["title"])}</h3></header>']
    if entry.get("detail"):
        parts.append(f'<p>{escape(entry["detail"])}</p>')
    meta = [f'<code>{escape(entry["key"])}</code>']
    meta.extend(f'<span class="tag">{escape(tag)}</span>' for tag in entry.get("tags", []))
    if entry.get("where"):
        meta.append(f'<code>{escape(entry["where"])}</code>')
    if entry.get("occurrences", 1) > 1:
        meta.append(f'seen {entry["occurrences"]}×')
    meta.append(f'updated <time>{escape(entry["updated"])}</time>')
    parts.append(f'<p class="meta">{" · ".join(meta)}</p>')
    notes = [h for h in entry.get("history", []) if h.get("note")]
    if notes:
        items = "".join(f'<li><time>{escape(h["at"])}</time> [{escape(h["status"])}] {escape(h["note"])}</li>' for h in notes)
        parts.append(f'<ul class="notes">{items}</ul>')
    parts.append("</article>")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Any path inside the project (default: cwd)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("path", help="Print the journal HTML path")
    listing = commands.add_parser("list", help="Show entries; DONE and IGNORED items only with --all")
    listing.add_argument("--all", action="store_true")
    add = commands.add_parser("add", help="Add an item, unless an open item with this key/title exists")
    add.add_argument("--key", required=True, help="Short stable slug for the item")
    add.add_argument("--title", required=True)
    add.add_argument("--detail", default="")
    add.add_argument("--where", default="", help="Location such as path/to/file.py:42")
    add.add_argument("--status", default="TODO", choices=("TODO", "DOING", "DONE"))
    add.add_argument("--note")
    add.add_argument("--tag", action="append", default=[], help="Kind of item, e.g. bug, idea, question (repeatable)")
    setter = commands.add_parser("set", help="Change an item's status")
    setter.add_argument("key")
    setter.add_argument("status", choices=STATUSES)
    setter.add_argument("--note")
    commands.add_parser("render", help="Rewrite the HTML from journal.json")
    arguments = parser.parse_args()
    journal = Journal(project_root(arguments.project))
    if arguments.command == "path":
        print(journal.html_path)
    elif arguments.command == "list":
        shown = [e for e in journal.entries if arguments.all or e["status"] not in COLLAPSED]
        for entry in shown:
            tags = "".join(f" #{tag}" for tag in entry.get("tags", []))
            print(f'[{entry["status"]}] {entry["key"]}: {entry["title"]}{tags}' + (f' ({entry["where"]})' if entry.get("where") else ""))
        if not shown:
            print("(no entries)")
    elif arguments.command == "render":
        print(journal.render())
    else:
        if arguments.command == "add":
            message = journal.add(arguments.key, arguments.title, arguments.detail, arguments.where, arguments.status,
                                  arguments.note, arguments.tag)
        else:
            message = journal.set(arguments.key, arguments.status, arguments.note)
        journal.save()
        print(message)
        print(journal.html_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
