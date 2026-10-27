# Agent skills

Reusable, optional skills for coding and research agents. The repository is
licensed under **AGPL-3.0-only**; see [LICENSE](LICENSE).

| Skill | Purpose |
| --- | --- |
| [web-design](web-design/SKILL.md) | Recommend and discuss a Bun/Tailwind v4 React stack, then build; optional self-hosted Convex bundle. |
| [frontend-design](frontend-design/SKILL.md) | Design and implement a deliberate visual interface. |
| [openai-ui-design](openai-ui-design/SKILL.md) | OpenAI-only UI design delegation to GLM through OpenCode, with recursion guards. |
| [jev](jev/SKILL.md) | Delegate typed semantic decisions and batches to Jev, with a portable Python client. |
| [reference-code](reference-code/SKILL.md) | Inspect existing examples and adapt relevant implementation patterns. |
| [reference-projects](reference-projects/SKILL.md) | Maintain reference checkouts and records of inspected revisions. |
| [tailscale-share](tailscale-share/SKILL.md) | Publish static artifacts privately through Serve or publicly through Funnel. |
| [html-publish](html-publish/SKILL.md) | Build a Tailwind v4 HTML artifact and publish a clickable link. |
| [matrix-notify](matrix-notify/SKILL.md) | Send personal Matrix notifications and tailnet links, including in encrypted rooms. |

## Optional, on-demand instructions

Installing a skill makes it available; it does not make its workflow mandatory.
Agents may choose a relevant skill, or a user may explicitly request one. Skill
hosts can show names and descriptions for discovery, then read the full
`SKILL.md` only when selected. Supporting resources are read only as needed.
No skill bodies are copied into an always-loaded `AGENTS.md` or system prompt.

This is normal automatic discovery with on-demand loading, rather than
explicit-invocation-only mode. A host may also offer individual enable/disable
controls. See [Codex skill discovery](https://developers.openai.com/codex/skills/)
and [OpenCode skills](https://opencode.ai/docs/skills/).

## Install

Clone this public repository to a location you control:

```bash
git clone https://github.com/muntedcrocodile/agent-skills.git
```

On a fresh setup, link the checkout into the discovery location your agent
supports. For example, current Codex uses `~/.agents/skills`; OpenCode uses
`~/.config/opencode/skills`. Preserve any existing skills and system bundles
when merging or repointing an existing directory. Individual skill folders can
also be linked instead of the entire checkout.

To include the library in another Git repository:

```bash
git submodule add https://github.com/muntedcrocodile/agent-skills.git skills
git submodule update --init --recursive
```

Each parent records a skills commit. Edit and commit inside the skills checkout,
push the skills repository, then update each parent's submodule pointer. A
parent stores the revision, not a second copy of the skill files in its history.

## Configuration and dependencies

Skills discover local context or use configurable paths; no particular personal
workspace, machine, or tailnet is assumed. Keep local configuration, credentials,
and generated output outside tracked source files.

Optional personal preferences can be kept in
`~/.config/agent-skills/config.json`, or another path selected with
`AGENT_SKILLS_CONFIG`. For example:

```json
{
  "reference-projects": {
    "checkouts": "~/.local/share/reference-projects/checkouts",
    "notes": "~/.local/share/reference-projects/notes"
  },
  "reference-code": {"directory": "~/reference-code"},
  "tailscale-share": {"root": "~/Public/agent-share"}
}
```

Environment overrides take precedence. Do not commit a personal configuration
to this public repository.

The sharing helper needs Python 3.10+ and the Tailscale CLI. It discovers the
current connected device's DNS name. Optional environment variables:

- `TAILSCALE_SHARE_TAILNET`: require a particular tailnet name before sharing.
- `TAILSCALE_SHARE_ROOT`: choose the local artifact folder; the default is
  `~/Public/agent-share`, with separate `tailnet/` and `public/` directories.
- `REFERENCE_PROJECTS_ROOT` and `REFERENCE_NOTES_ROOT`: reference checkout and
  note locations used by the research skills.
- `REFERENCE_CODE_DIR`: an additional existing directory of code examples.

Tailscale account enrollment, access policy, and HTTPS availability belong to
the user's environment. Sharing is private by default. Public publishing needs
a user request and uses a separate Funnel endpoint. Running the helper modifies
that local sharing configuration; merely installing or reading the skill does
not publish anything.

The HTML starter uses Tailwind v4's browser package for prototypes. The skill
also describes compiling CSS for durable or offline artifacts. Git is needed
for reference-repository workflows.

Matrix notifications use the pinned `matrix-nio[e2e]` dependency. Run
`matrix-notify/scripts/setup.sh`, copy its `.env.example` to a private env file,
and run `matrix-notify/scripts/notify.sh init` once to create a dedicated device.
The default env path is `~/.config/agent-skills/matrix.env`; keep the actual
credentials and persistent device store outside this public checkout. See the
skill for overrides and the HTML-to-tailnet workflow for long reports.

## Develop and verify

```bash
python3 -m unittest discover -s tests -v
bun test web-design/tests
```

Tests use temporary directories and a fake Tailscale CLI; they do not configure
a real network endpoint. Before publishing a change, review every tracked file
for credentials, personal hostnames, addresses, tailnet names, private paths, and
generated artifacts. Use neutral fixtures and placeholders in examples. Third-
party system/plugin skills are not distributed or relicensed by this project.
