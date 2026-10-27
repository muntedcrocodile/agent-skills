# Stack choices

This template is extracted from Behaviour's implementation: Bun, React, Vite,
React Router, strict TypeScript, Tailwind v4 through its Vite plugin, shadcn/ui
on Radix primitives, and optional self-hosted Convex. Its additional tools were
Better Auth's Convex component, Recharts, Lucide, Sonner, vite-plugin-pwa,
Bun tests, convex-test, and Playwright. They are options, not a dependency list
to install in every project. Do not copy Behaviour's domain schema, account
roles, personal settings, licensed fonts, or credentials.

## Choose the frontend

Use **React + Vite** when browser rendering and a small amount of routing are
sufficient: local visualisations, calculators, internal dashboards, or focused
interactive apps. React Router can supply navigation without Framework Mode.
Convex can supply the backend independently. The normal static build is `dist/`.
Configure a hosting fallback to `index.html` when using browser-history routes;
check direct links and refreshes, not just navigation from the home page.

Use **React Router Framework Mode** when route-level structure, generated route
types, loaders/actions, splitting, prerendering, or SSR help the product. Select
the rendering strategy explicitly:

- SPA (`ssr: false`): browser app, static hosting, normally `build/client/`.
  The build still renders the root route; guard browser-only code and keep
  browser storage out of module scope and the initial build-time render.
- Prerendering: useful for known public routes where build-time HTML is enough.
- SSR: useful when request-time HTML or server handling is needed; plan and
  validate the server runtime, proxy, and deployment as well as the browser build.

Framework Mode uses the React Router Vite plugin, rather than copying the
lightweight starter's React plugin configuration verbatim. Generate route types
before checking TypeScript. Do not introduce a second data cache or an extra API
layer by habit when Convex subscriptions already cover the server state.

Examples of recommendations to discuss with the user:

- “This CSV explorer can run entirely in the browser. I recommend React + Vite,
  Bun, and Tailwind v4 with file import and no backend. Shall we use that?”
- “This application has several nested workflows and shared live data. I
  recommend React Router Framework Mode in SPA mode with self-hosted Convex.
  That gives us route structure without requiring an SSR server. Does that fit?”

These are examples of reasoning, not rules based solely on the number of pages.
If the conversation already approved a suitable stack, proceed on that basis.

## Build conventions

Record compatible dependency versions in `package.json` and `bun.lock`; check
current official docs before scaffolding rather than treating reference-project
versions as permanently current. Use `bun install`, `bun add`, `bun run`, and
`bunx --bun` for tooling. Preserve the approved project's lockfile conventions
when working in an existing codebase; discuss a necessary migration first.

For Tailwind v4 install `tailwindcss@4` and `@tailwindcss/vite@4`, add the plugin
to the selected Vite configuration, and import `tailwindcss` in the app CSS.
Use CSS theme variables and a consistent theme selector for dark/light styling.
Compile CSS into the build; do not ship the browser Tailwind compiler.

Use shadcn/ui with its Tailwind v4 setup for React components. Recharts can serve
ordinary interactive charts; choose something else if the data/interaction
requires it. Add vite-plugin-pwa only when installation or offline support is
requested, with an explicit cache/update policy. Authentication through Better
Auth's Convex component is an option for Convex apps, not a requirement for
viewing a local dataset.

## Hosting and data

Local visualisations should avoid service dependencies. A user-selected file
can stay in the browser; bundled data becomes downloadable by anyone with access
to the site. Pick the intended approach during the stack discussion.

For a shared application, persist authoritative data on the backend and enforce
access there. Separate development and production data, credentials, and Compose
project names. Prefer reproducible self-hosted deployment when it fits the user's
environment. Behaviour used Docker Compose and HTTP Nginx behind an existing TLS
proxy; do not assume that upstream proxy exists on every target machine.

## Official references

- [React Router modes](https://reactrouter.com/start/modes)
- [React Router SPA deployment](https://reactrouter.com/how-to/spa)
- [Vite](https://vite.dev/guide/)
- [Bun](https://bun.sh/docs)
- [Tailwind v4 Vite integration](https://tailwindcss.com/docs/installation/using-vite)
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite)
- [Better Auth with Convex and React](https://labs.convex.dev/better-auth/framework-guides/react)
