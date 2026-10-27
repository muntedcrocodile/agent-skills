---
name: matrix-notify
description: Send the user a Matrix notification, update, result, or link when they say "notify me", "send me", "message me", or ask for delivery through Matrix. Use the configured personal notification room; ordinary answers in the current chat alone do not request a notification, and an explicitly named delivery channel takes precedence.
license: AGPL-3.0-only
---

# Matrix notifications

Deliver requested information to the user's configured Matrix room using
`scripts/notify.sh`. Resolve paths relative to this skill, including through
symlinks. Requests such as "notify me when it finishes" authorize that notification
when the work finishes; send it without asking for the same permission again.
"Send me the report" uses Matrix unless the user selected another channel.
Send only the requested material. This skill does not set up recurring work or
send messages to other people.

## Send

```bash
bash /path/to/matrix-notify/scripts/notify.sh check
bash /path/to/matrix-notify/scripts/notify.sh send --message 'The job finished successfully.'
bash /path/to/matrix-notify/scripts/notify.sh send --file /absolute/path/notification.txt
```

For arbitrary generated text, use a file or stdin (`send --file -`) so shell
expansion cannot alter the message. Use a short title/context, the result, and
any useful link. A successful JSON result includes `status: sent` and an
`event_id`; that means the homeserver accepted it, not that the user read it.
After sending, acknowledge delivery briefly in the current conversation.

For a **complex or long breakdown**, create a standalone HTML file with the
sibling [`html-publish`](../html-publish/SKILL.md) skill, publish it using
[`tailscale-share`](../tailscale-share/SKILL.md), and send a brief summary plus
the verified HTTPS link in Matrix. Do this instead of pasting a large report or
splitting it into many messages. Tell the recipient the link requires their
tailnet connection. Keep publishing private to the tailnet unless the user
explicitly requested public access. If publishing fails, report the failure;
do not silently substitute public hosting or claim that the report was delivered.
Honor an explicit request for inline text or a different format when feasible.

## Initial setup and credentials

Python 3.10+ is required. Install dependencies once:

```bash
bash /path/to/matrix-notify/scripts/setup.sh
```

Copy [`.env.example`](.env.example) to a private `.env` file outside the skill
checkout, set its values, and `chmod 600` it. The default location is
`~/.config/agent-skills/matrix.env` (respects `XDG_CONFIG_HOME`); this can be a
symlink to the project's ignored credential file. Select another path with
`MATRIX_NOTIFY_ENV_FILE` or `notify.sh --env-file /private/path/.env ...`.
Process `MATRIX_*` variables override file values. Env files contain literal
assignments, not shell commands; never source them or print their contents.

`MATRIX_HOMESERVER`, `MATRIX_USER_ID`, and `MATRIX_ROOM_ID` are required.
Set `MATRIX_HOMESERVER` to the homeserver's canonical public HTTPS base URL
(for example, `https://matrix.example.org`) on every host, including the server
itself. Verify it from each sending machine. Loopback addresses, Docker service
names, LAN IPs, and tailnet-only addresses are not portable to other agents;
do not substitute one when the public endpoint fails.
`MATRIX_HOME_ROOM` and `MATRIX_HOME_ROOM_THREAD_ID` are accepted as destination
aliases for existing Hermes configurations. A thread ID is optional.

Run `notify.sh init` once with `MATRIX_PASSWORD` set privately. This creates a
dedicated notification device and saves its token and encryption keys under
`~/.local/share/agent-skills/matrix-notify` (respects `XDG_DATA_HOME`), or
`MATRIX_NOTIFY_STATE_DIR`. Existing access tokens/device IDs in imported env files
are deliberately not reused: other clients own their encryption state. Preserve
the notification session and its store together. After initialization the password
can be removed from this integration's env file. Never copy the same device store
between concurrently active hosts; initialize a separate device on each host.
`init` is idempotent when a session already exists. `check` validates access and
room state without posting a message. The account must already be joined to the
configured room; the helper does not invite people or create rooms.

Existing sessions are bound to their configured homeserver URL. When correcting
an address for the same server, first verify the existing token's authenticated
`/_matrix/client/v3/account/whoami` response over the public HTTPS endpoint
matches the saved user and device IDs. Back up the private env file and session,
then update `MATRIX_HOMESERVER` and the session's `homeserver` together while the
device is idle. Retain its token, device ID, and encryption store, and run
`check` before sending. A different server or account needs a separate state
directory. Never print tokens while performing this check.

The helper supports encrypted rooms through matrix-nio and keeps persistent keys.
It shares encrypted delivery keys with joined members' unverified devices by
default, without marking those devices verified. Set
`MATRIX_ALLOW_UNVERIFIED_DEVICES=false` to require verification in the nio store.
HTTPS is the default; `MATRIX_ALLOW_HTTP=true` is an explicit option for trusted
transports such as HTTP carried inside Tailscale. Never disable TLS certificate
verification. `MATRIX_NOTIFY_VENV` selects a different dependency environment for
both setup and delivery.

## Failures

The client bounds network retries and serializes access to its local device.
If a send fails or times out, preserve the printed transaction ID and retry the
**same** message with `--transaction-id ID`; a new ID can duplicate an accepted
delivery. Stop after one manual retry and report the remaining failure. Do not
keep logging in, replace another client's device keys, dump server responses,
or claim success without a returned event ID. Keep credentials and device stores
out of Git, published HTML, and notification content.

References: [Matrix client-server API](https://spec.matrix.org/latest/client-server-api/),
[matrix-nio encrypted client examples](https://matrix-nio.readthedocs.io/en/latest/examples.html).
