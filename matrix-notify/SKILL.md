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
splitting it into many messages. Keep publishing private to the tailnet unless the user
explicitly requested public access. If publishing fails, report the failure;
do not silently substitute public hosting or claim that the report was delivered.
Honor an explicit request for inline text or a different format when feasible.

References: [Matrix client-server API](https://spec.matrix.org/latest/client-server-api/),
[matrix-nio encrypted client examples](https://matrix-nio.readthedocs.io/en/latest/examples.html).
