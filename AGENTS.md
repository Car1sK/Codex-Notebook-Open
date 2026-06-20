# AGENTS.md

Guidance for agents working in this workspace.

## Workspace Layout

This root is a private meta Git repository for the integration layer:

<https://github.com/Alasyoki/Codex-Notebook-Open>

It contains three embedded upstream Git repositories that remain independent and are ignored by the root `.gitignore`:

| Directory | Purpose |
|---|---|
| `Hermes_agent/` | Local Hermes Agent deployment |
| `opennotebook/` | Open Notebook project |
| `notebooklm-py/` | NotebookLM Python client project |

## Product Goal

This workspace is a local integrated application built from `opennotebook/`, `notebooklm-py/`, and `Hermes_agent/`.

The intended user experience is:

1. The user manages sources, notebooks, and final notes in the Open Notebook web UI.
2. Agents connect through the local `notebooklm-py` CLI/MCP bridge instead of asking the user to run complex commands.
3. Agents may list/create notebooks, import source material, manage notes when asked, inspect state, and verify that Open Notebook operations completed. Source imports should default to asynchronous Open Notebook processing so the agent does not block on long ingestion work.
4. Agents must not treat Open Notebook as an automatic note-authoring pipeline. Final organization and authored notes remain user-controlled unless the user explicitly asks for agent-written notes.
5. Rhet and other ad hoc folders are test material only unless explicitly brought back into scope.
6. TTS/STT is not part of the normal acceptance criteria unless the user explicitly asks for an audio capability check.

## Local Operations

- User-facing entrypoints should be root-level `.bat` files. Keep PowerShell/Python implementation helpers under `scripts/` unless a root wrapper is required for Codex/Hermes compatibility.
- Use `OpenNotebookLM.bat` as the normal user-facing launcher. It detects first run versus later runs, installs or repairs missing local dependencies, then starts the full Open Notebook + Ollama + Codex MCP + Hermes stack.
- Keep Open Notebook startup idempotent. `start_open_notebook.bat` protects launcher, backend, and frontend startup with `launcher.lock`, `backend.lock`, and `frontend.lock` under `open-notebook-data/`; repeated calls should wait for or reuse ports `5055` and `3000` instead of spawning duplicate backend/frontend windows.
- Use `OpenNotebookLM.bat --setup-only` to install or repair missing dependencies without starting services, `OpenNotebookLM.bat --force-setup` to force setup checks without reinstalling already-present environments, and `OpenNotebookLM.bat --check` for the read-only local stack check.
- The other root `.bat` files are component-level maintenance entrypoints for targeted debugging: `start_open_notebook.bat`, `start_local_agent_stack.bat`, `start_ollama_models.bat`, `setup_hermes_open_notebook_mcp.bat`, `setup_codex_open_notebook_mcp.bat`, `check_local_agent_stack.bat`, `start_hermes.bat`, and `stop_hermes.bat`.
- Refresh the Codex MCP connection with `setup_codex_open_notebook_mcp.bat` after changing the local Open Notebook password or updating `notebooklm-py`.
- Open Notebook runtime configuration is loaded from `opennotebook/.env`. Never print or commit `OPEN_NOTEBOOK_ENCRYPTION_KEY` or passwords.
- The local NotebookLM bridge consists of a versioned bundle contract plus direct Open Notebook source/note-management CLI/MCP tools. See `open_notebook_codex_integration_guide.html` for operator commands and `notebooklm_open_notebook_integration_analysis.html` for system boundaries.
- This workspace does not use GitHub Issues as its task tracker. Do not create or depend on issues unless the user explicitly changes that decision.

## Codex + Hermes Collaboration

Use Hermes as the primary implementation worker for eligible low- and medium-risk programming tasks through the externally enforced delegation state machine, then let Codex review and verify the result. Codex is the only final approver.

Default workflow:

1. For eligible implementation tasks, Codex assigns `simple`, `medium`, or `specialist`, then calls `delegate_to_hermes.bat` or `delegate_to_hermes.ps1 -AllowEdits` with explicit `-AllowedPaths` and a trusted `-VerifyCommand` after minimal scope and safety triage.
2. The launcher owns sequencing: simple tasks use a Flash implementer; medium and specialist tasks use a Pro planner, Pro implementer, trusted verification, and a fresh Pro review session.
3. The launcher fingerprints the repository, rejects out-of-scope changes, captures process output and exit codes, and permits at most one focused Pro repair pass.
4. Timeout, no response, malformed handoff, missing changes, failed verification, or rejection after repair returns ownership to Codex immediately.
5. Codex does not duplicate a successful implementation. It reviews the saved gate artifacts, working-tree diff, repository rules, and verification evidence, then runs the narrowest independent check proportional to risk.
6. Codex reports the assigned classification, completed phases, changed files, accepted or rejected work, and both layers of verification.

WorkDir selection is part of the safety boundary:

- Use `D:\applyandcreate\workplace\OpenNotebookLM` only for root integration-layer files.
- Use `D:\applyandcreate\workplace\OpenNotebookLM\Hermes_agent` for Hermes Agent changes.
- Use `D:\applyandcreate\workplace\OpenNotebookLM\notebooklm-py` for NotebookLM bridge changes.
- Use `D:\applyandcreate\workplace\OpenNotebookLM\opennotebook` for Open Notebook application changes.
- Do not use root `AllowedPaths` such as `.`, `./`, or repository root; pass explicit files or directories.

Good delegation candidates:

- Small and medium bug fixes with a clear symptom
- Simple script or helper creation
- Small test additions
- Localized refactors in one or two files
- Clear multi-file behavior changes within one repository
- Straightforward usage examples

Do not delegate by default:

- Secret handling, auth, or credential changes
- Destructive filesystem or git operations
- Large architecture changes
- Broad multi-repo refactors
- Ambiguous product decisions
- Tasks where the user explicitly wants Codex to work directly

Current Hermes quality profiles:

- Provider: DeepSeek
- Simple implementation: `deepseek-v4-flash`
- Medium/specialist planning, implementation, review, and repair: `deepseek-v4-pro`
- Final approval: Codex
- Terminal backend: `local`
- Start script: `start_hermes.bat`
- Stop script: `stop_hermes.bat`
