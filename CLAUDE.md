<!-- >>> engine: the engine's standing rules — this block is maintained by engine.py; write project text below the end marker -->
@.claude/engine-rules.md
<!-- <<< engine -->

@AGENTS.md
@.engine/rules.md

# <project name>

<One sentence: what this project is and for whom.>

## Conventions every agent must know

- Stack and the commands that run it: `<install>`, `<test>`, `<lint>`, `<type-check>`.
- Source lives in `<src/>`; tests in `<tests/>`. `.claude/project.env` names them for the hooks.
- Paths that must never be edited by an agent beyond the engine's own list (migrations,
  generated code, vendored copies): add them to `.claude/hooks/protect-paths.sh`.
- Anything domain-specific every session should know by default goes here, briefly.
  Detail that is rarely needed goes in `docs/` and is read on demand.
