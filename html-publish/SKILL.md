---
name: html-publish
description: Create and publish a standalone HTML plan, explanation, comparison, or interactive visualization with Tailwind CSS v4 and a clickable Tailscale link. Use when HTML helps communicate the result or the user asks for a shareable HTML artifact.
license: AGPL-3.0-only
---

# HTML publish

Create an HTML artifact, save it, and publish it using the sibling
[`tailscale-share`](../tailscale-share/SKILL.md) skill. Read that skill before
publishing. Keep the result useful as a document: concrete content, readable
typography, responsive layout, and semantic controls. Add interaction when it
helps explore the information. For exported scientific figures, use a plotting
tool and embed or link the result.

## Tailwind v4 without a build step

Copy `assets/starter.html` into a task-specific output directory outside the
publishing folders. Replace its example title and content. It includes:

```html
<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
<style type="text/tailwindcss">
  @theme { --color-accent: #075985; }
</style>
```

This is the **v4 browser package**. Do not use the v3 `cdn.tailwindcss.com`
script or a v3 `tailwind.config` snippet. The browser package requires internet
access to jsDelivr; tailnet connectivity alone does not supply that dependency.
Keep important text readable with the starter's ordinary CSS if the CDN fails.
Inline small scripts and SVGs; use relative paths for bundled assets. Do not
include API keys or require a development server to open the result.

The Play CDN is intended for development and prototypes. It suits personal
plans and quick visualizations. For durable/public production artifacts or
offline styling, compile CSS with the official v4 CLI in a temporary build
directory, then publish only the static output:

```bash
npm install --save-dev tailwindcss@4 @tailwindcss/cli@4
# input.css: @import "tailwindcss"; and @source "./index.html";
npx @tailwindcss/cli -i ./input.css -o ./styles.css --minify
```

Reference the generated `styles.css`, remove the browser CDN script and
`text/tailwindcss` block, and move any `@theme` rules into input.css before
compiling. Use full utility class strings so the scanner can find them. Retain
the build inputs in the task workspace; exclude node_modules and package
manifests from the publication bundle.

## Save, check, publish

1. Write `index.html` and its assets to a task output directory. State real
   assumptions and decisions in the content; do not leave template examples.
2. Preview in a browser when available. Check narrow and wide layouts, main
   interactions, and console/network errors. Without a browser, inspect the
   markup and links and disclose the limits of validation.
3. Use `tailscale-share/scripts/publish.py publish /absolute/path/output --name
   descriptive-slug`. Publish on the tailnet unless the user requested public
   access; then use that skill's `--public` option. The complete output directory
   is copied so relative assets work.
4. Return a short Markdown link to the page and identify tailnet/public access.
   Include any material dependency or hosting limitation. Do not finish with
   only a local file path when publishing was requested.

References: [v4 Play CDN](https://tailwindcss.com/docs/installation/play-cdn),
[v4 CLI](https://tailwindcss.com/docs/installation/tailwind-cli).
