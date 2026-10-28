---
name: tailscale-share
description: Publish a file or static website at a clickable HTTPS link on the user's Tailscale tailnet, or publicly through Funnel when public access is requested. Use for viewing and downloading artifacts; use Taildrop separately for one-off device transfers.
license: AGPL-3.0-only
---

# Tailscale sharing

Use the bundled `scripts/publish.py` with Python 3 (standard library only).
Resolve its path relative to this SKILL.md, including when this skill is symlinked.
Publishing uses the currently connected tailnet. Inspect the active identity
and follow any tailnet specified by the user. Set `TAILSCALE_SHARE_TAILNET` to
require a particular tailnet; the helper discovers the device DNS name at runtime.
Local preferences can also live in `~/.config/agent-skills/config.json` under
`tailscale-share`, with optional `tailnet` and `root` fields. Environment variables
take precedence. `AGENT_SKILLS_CONFIG` selects a different local config file.

## Publish

```bash
python3 /path/to/tailscale-share/scripts/publish.py publish /absolute/path/report.pdf --name report
python3 /path/to/tailscale-share/scripts/publish.py publish /absolute/path/static-site --name project-plan
```

Use a distinct lowercase slug for each publication. Directories preserve relative
assets; put `index.html` at the root for a site. The helper copies the artifact,
checks the tailnet, configures a persistent endpoint, checks for route conflicts,
and fetches the result before printing the link. Return that URL as a Markdown link.
If verification fails, report that failure and the URL; do not call it verified.
Avoid overwriting an earlier publication; choose another slug for a revision.

The always-shared directory is `~/Public/agent-share/tailnet`, on HTTPS port 8444.
After `init`, files copied directly there are immediately available, including new
files, without restarting a service. Only put intended shared artifacts there.
Tailnet access follows Tailscale policy: the receiving device must be connected
and permitted to reach this host on port 8444. These folders are hosted locally;
Tailscale does not sync them to other machines. The publishing host must be awake
and online. A background Serve configuration persists across daemon restarts.

## Public option

When the user asks for internet/public access, add `--public` to the publish
command. This uses Funnel on port 8443 with the separate directory
`~/Public/agent-share/public`. Anyone with the link can access it, without joining
the tailnet. Public mode shares every artifact in that directory. Include only
the requested artifact and its dependencies. Never Funnel the tailnet folder or
the parent `agent-share` folder. No extra confirmation is needed when the user
has already requested public publishing.

Funnel requires HTTPS, MagicDNS, and the user's Funnel permission in tailnet
policy. If unavailable, report the specific prerequisite; do not edit tailnet
policy, switch accounts, or fall back to public sharing for a private request.

## Operations

```bash
python3 /path/to/tailscale-share/scripts/publish.py init
python3 /path/to/tailscale-share/scripts/publish.py status
python3 /path/to/tailscale-share/scripts/publish.py stop
python3 /path/to/tailscale-share/scripts/publish.py stop --public
```

Remove a publication by deleting its named subdirectory, then check that its URL
returns 404. Stopping an endpoint retains files; starting it again re-shares them.
Do not use `tailscale serve reset` or `tailscale funnel reset`, which affect other
applications. The helper refuses unrelated routes on its ports, symlinks, hidden
files, and non-regular files. Inspect bundles for secrets before publishing.

Overrides: `TAILSCALE_SHARE_ROOT` changes the parent folder and
`TAILSCALE_SHARE_TAILNET` requires an explicitly intended tailnet. Use the same values on every invocation. To move
the shared folder, stop the old endpoint before changing the root.

On a disconnected machine, use `sudo tailscale up` and let the user complete the
account sign-in. For direct filesystem serving, the helper retries only the
specific Serve/Funnel command with `sudo -n` if Tailscale requires root. It never
runs the Python helper as root. If passwordless sudo is unavailable, report the
command for an administrator to run. On macOS, direct directory serving requires
the open-source Tailscale variant; other variants need a persistent localhost
static server and a Serve proxy, outside this helper's automated baseline.

References:
[Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[Funnel](https://tailscale.com/docs/features/tailscale-funnel).
