---
name: openai-ui-design
description: OpenAI models only. Use before any UI/UX or frontend visual design work, including layout, styling, typography, components, responsive design, and visual polish. Never applies to non-OpenAI models. Only to be used for new visual design and not for technical implementation.
license: AGPL-3.0-only
---

# OpenAI UI design delegation

## Check the executing model first

This skill applies only when the agent executing it is an OpenAI model. Use
trusted runtime/model information; running inside Codex or being asked about
OpenAI does not establish the model's identity. If the identity is unknown,
establish it before launching a delegate.

GLM and all other non-OpenAI models must ignore this delegation workflow,
including when explicitly asked to read this skill. They should perform the
design themselves using `frontend-design`. Never launch another GLM instance
from a GLM design delegate.

Complete the assigned design directly using `frontend-design`.

## Delegate the design

For OpenAI models, use this workflow whenever the task involves UI design
decisions, even within a larger implementation task. It covers new interfaces,
redesigns, layouts, styling, typography, component appearance, and visual polish.
Pure backend work or UI logic changes that require no design decisions do not trigger delegation.

Inspect the relevant project context and give the design model a concrete brief: the user's
goal, affected files, framework, existing components/design tokens, visual
constraints, acceptance criteria, and whether to propose a design or implement
it. Work from the intended project directory. Explicitly include these
instructions in the brief:

> Use your `frontend-design` skill. You are the delegated UI designer; complete
> this design yourself. Do not use `openai-ui-design` or launch another design
> delegate. Stay within the assigned files and the user's authorized task.


in t3 start a subagent of `openrouter/z-ai/glm-5.3-flash` using the opencode harness.


If you cannot launch it as a t3 subagent launch it directly via commandline:
```bash
OPENAI_UI_DESIGN_DELEGATED=1 opencode run --model openrouter/z-ai/glm-5.3-flash "$design_brief"
```

`openrouter` is the OpenCode provider ID; `z-ai/glm-5.3-flash` alone is not a
complete OpenCode model selector. Preserve the full selector shown above.

Review the delegate's output, integrate the changes, and verify the resulting
interface and behaviour. The OpenAI parent retains responsibility for the
technical work and final result. Send any necessary design revision back to
GLM as a bounded follow-up; do not create nested delegation chains.

If OpenCode or the selected model is unavailable, report the concrete failure
and perform the design directly with `frontend-design`. Do not keep relaunching
a failed command or silently substitute another model.
