---
name: journal
description: This is a skill for how to manage a per-project journal of tracked items (bugs, follow-ups, ideas, questions, decisions, or anything worth recording) with statuses. Use when the user says to log, note, journal, or track something for later, to update or review journal items, or to share the journal or if an exisitng journal is present.
license: AGPL-3.0-only
---

# Project journal

A lightweight, per-project record of items with a status. What goes in it is up
to the user or the instructions that send you here: noticed bugs, follow-ups,
ideas, open questions, decisions, or progress notes. Record items briefly and carry
on with the current task unless told to act on them.

Each project has one journal: `.agent-journal/` at the Git top level (or the
current directory outside Git). `journal.json` holds the entries and
`index.html` is rendered from [`assets/journal.html`](assets/journal.html).
Change entries only through `scripts/journal.py` (Python 3, standard library),
resolving its path relative to this SKILL.md, including through symlinks. It
applies the rules below and re-renders the HTML after every change. The first
write adds `/.agent-journal/` to the repository's local `info/exclude`, so the
journal stays out of commits without editing `.gitignore`.

## Statuses

| Status | Meaning | Shown in |
| --- | --- | --- |
| `[TODO]` | Recorded, still to be dealt with. The default. | Active |
| `[DOING]` | Being worked on now. | Active |
| `[REOCCURED]` | Was `[DONE]` but came up again. Set automatically. | Active, first |
| `[DONE]` | Finished or resolved. | Collapsed **Done** section |
| `[IGNORED]` | The user chose to keep it on record but not act on it. Set only when the user asks. | Collapsed **Ignored** section |

## Add an item

1. Run `list` first. If the item is already there, reuse its key.
2. Add it with a short, stable key and a one-line title. Optionally add detail,
   a location (file and line, URL, or other reference), and one or more tags
   that say what kind of item it is:

```bash
python3 /path/to/journal/scripts/journal.py list
python3 /path/to/journal/scripts/journal.py add --key retry-on-timeout \
  --title "Upload client gives up after one timeout" --tag bug \
  --where src/upload.py:88 --detail "Should retry with backoff before failing."
python3 /path/to/journal/scripts/journal.py add --key cache-design \
  --title "Decide whether the cache is per-user or global" --tag question
```

`add` never creates a duplicate. If a matching key or title exists with any
status except `[DONE]`, including `[IGNORED]`, it changes nothing and reports the
existing item, so ignored items stay quiet. If the match is `[DONE]`, the item
moves back to the active section as `[REOCCURED]`. New items are `[TODO]` unless
`--status DOING` or `--status DONE` fits better.

## Update a status

```bash
python3 /path/to/journal/scripts/journal.py set retry-on-timeout DOING
python3 /path/to/journal/scripts/journal.py set retry-on-timeout DONE --note "Fixed in a1b2c3d"
# Only when the user says to ignore it:
python3 /path/to/journal/scripts/journal.py set cache-design IGNORED --note "User: not now"
```

`[DONE]` and `[IGNORED]` items move to their own sections, which start
collapsed. `list` omits them; use `list --all` to include them, and `render` to
rebuild the HTML after editing the template.

## Share the journal

Make and publish the page with the sibling
[`html-publish`](../html-publish/SKILL.md) skill. The journal uses this skill's
template in place of html-publish's starter file. Follow html-publish's "Save,
check, publish" steps for `index.html` (path printed by `journal.py path`). Use
the name `journal-<project-slug>` with `--replace`, so each project keeps one
stable link that updates in place:

```bash
python3 /path/to/tailscale-share/scripts/publish.py publish "$(python3 /path/to/journal/scripts/journal.py path)" \
  --name journal-my-project --replace
```

Return the printed folder URL (ending in `/journal-<project-slug>/`) as a
Markdown link. The journal is tailnet-only unless the user
asks for public access. Never put secrets, credentials, or private data in entries.
