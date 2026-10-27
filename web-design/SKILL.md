---
name: web-design
description: Plan and build framework-based websites, web apps, and interactive local-data visualisations with Bun and Tailwind CSS v4. Recommend a suitable stack and consult the user before implementation; includes an optional self-hosted Convex setup. Use for new projects or substantive architecture changes, not routine styling fixes in an established stack.
license: AGPL-3.0-only
---

# Web design and implementation

## Think through the stack, then consult the user

Inspect the existing project and the intended experience before choosing tools.
Consider the audience, interactions, routing, search visibility, rendering,
data source, persistence, authentication, offline needs, and hosting environment.
Read [stack choices](references/stack.md) when making the recommendation.

Recommend the stack you think best fits this use case. Explain the consequential
tradeoffs and what runs in the browser versus on a server. Present the proposed
framework, rendering mode, data/backend choice, and hosting approach to the user
**before scaffolding, installing dependencies, or implementing the site**. Ask
for their view or agreement; wait for the response. Read-only inspection and
research may continue. Existing explicit stack approval in this conversation
satisfies this step; do not ask again unless the proposal materially changes.

Both of these are supported choices, with neither universally preferred:

- **React Router Framework Mode with Vite:** route modules, typed route APIs,
  code splitting, and a path to prerendering or server rendering. SPA mode is
  appropriate when runtime server rendering adds no value.
- **React + Vite:** the lighter Behaviour-style setup, adding React Router in
  library mode when navigation needs it. A good fit for focused browser tools,
  visualisations, and client-rendered apps backed by Convex.

Always use a component framework/library; both React options satisfy this rule.
Do not deliver a hand-written standalone HTML/JavaScript app as a substitute.
Another framework may be proposed when it is a better fit, with reasons and user
agreement. Preserve an established project's architecture for ordinary changes;
do not turn a styling request into an unsolicited migration.

## Shared implementation requirements

- Always use **Bun** for package management, project scripts, and tooling. Commit
  `bun.lock`, record the Bun version, and use frozen installs for reproducible
  builds. Use Bash for shell commands. Convex functions still use Convex's runtime.
- Always use **Tailwind CSS v4**, compiled through `@tailwindcss/vite` for these
  Vite stacks. Use the v4 CSS import and theme conventions, not a v3 setup or
  browser CDN in the delivered app.
- Use strict TypeScript with concrete types; do not use `any` to bypass checks.
  Prefer shadcn/ui components for the React options and reuse existing components.
- Carry forward Behaviour's light/dark theme support, defaulting to dark for new
  apps unless the user or existing product specifies otherwise. Treat its font
  preference as project-specific, not a mandatory font for unrelated websites.
- Keep technical configuration, deployment, schema, migrations, and scheduled
  jobs in project files and executable commands. Secrets belong in ignored
  configuration; provide templates. Do not require dashboard-only setup.

## Choose data storage deliberately

For local files, supplied JSON/CSV, or existing data that the app only visualises,
**do not add Convex**. Load the data in the browser or bundle it at build time;
use component state and, only when useful, browser storage for local preferences.
Discuss data size and privacy if they affect how files are loaded or shared.

Self-hosted Convex is a strong option when the app needs durable shared state,
live subscriptions, authenticated writes, server functions, or scheduled jobs.
Its use must follow from the requirements, not from the existence of a template.
If chosen, read [self-hosted Convex](references/convex.md) and adapt the bundled
[setup assets](assets/convex-self-hosted/). They include Compose, pinned backend
and proxy images, private configuration, and CLI access. Do not copy them into
a project that does not need Convex. Add authentication, PWA support, charts,
and notifications only when the product needs them.

## Design, implement, and verify

After the stack discussion, use the companion `frontend-design` skill for visual
direction and interface quality. OpenAI models must first follow the companion
`openai-ui-design` skill's GLM delegation workflow; other models design directly
and must not recursively delegate. These companions are provided by this skill
library. Keep the agreed stack and scope in the design brief.

Implement the real content and primary interactions. Include accessible controls,
keyboard focus, responsive layouts, and appropriate loading, empty, and error
states. Keep the dev preview available during development when the environment
supports persistent processes; record its address and logs.

Run the appropriate Bun typecheck/build and meaningful behaviour tests. Inspect
the actual interface at narrow and wide sizes and exercise its main interaction
with the environment's browser tools. For Convex, verify a write/read and
persistence across a restart; for local visualisations, verify they work without
backend services. Report any unverified parts plainly.

Use the approved hosting target. Sharing defaults to private/tailnet access;
public deployment requires the user's request. A static build can be shared
without deploying an app server. An SSR build needs its runtime and cannot be
published as a directory of browser files alone.
