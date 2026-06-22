# Codex Notebook Open

English | [中文](README.zh-CN.md)

Codex Notebook Open is a local Windows launcher and integration bundle for:

- [Open Notebook](https://github.com/lfnovo/open-notebook)
- [notebooklm-py](https://github.com/teng-lin/notebooklm-py)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [Ollama](https://ollama.com/) local embeddings

The goal is a practical local stack: users manage sources, notebooks, and final notes in the Open Notebook web UI; Codex and Hermes can connect through the local notebooklm-py CLI/MCP bridge for controlled automation.

## What is included

- One-click Windows entrypoint: `OpenNotebookLM.bat`
- Integrated setup/check/start/stop flow through `OpenNotebookLM.bat`
- Source snapshots of the three upstream runtime projects under `components/`
- Local MCP setup helpers for Codex and Hermes
- No local database, no secrets, no virtual environments, no `node_modules`, and no generated HTML reports

The bundled snapshots are trimmed for local runtime use. Large upstream test suites, recorded fixtures, documentation sites, generated reports, and Hermes bundled skills are not included.

## Quick start (macOS / Linux)

```bash
git clone https://github.com/Car1sK/Codex-Notebook-Open.git
cd Codex-Notebook-Open
./OpenNotebookLM.sh
```

Then open `http://localhost:3000`.

The POSIX launcher supports the same modes as the Windows .bat:

```bash
./OpenNotebookLM.sh --setup-only
./OpenNotebookLM.sh --check
./OpenNotebookLM.sh --check-live
./OpenNotebookLM.sh --start-open-notebook
./OpenNotebookLM.sh --setup-codex-mcp
./OpenNotebookLM.sh --setup-hermes-mcp
./OpenNotebookLM.sh --start-hermes
./OpenNotebookLM.sh --stop-hermes
./OpenNotebookLM.sh --stop
./OpenNotebookLM.sh --help
```

Windows users should use `OpenNotebookLM.bat` (see the section below).

## Prerequisites

Before using `OpenNotebookLM.bat`, ensure a fresh Windows 10/11 system has the following tools. `winget` is the recommended Windows setup path because the launcher can use it to install several missing external tools automatically.

| Tool | Status | Purpose |
|------|--------|---------|
| Git | Required | Clone the repository and manage version control |
| Python 3.11 or 3.12 | Required | Run the launcher and create the Open Notebook / Hermes Python environments |
| PowerShell 5+ | Required | Script execution during setup; included with Windows 10/11 |
| winget | Recommended | Windows Package Manager; lets the launcher install Node.js, SurrealDB, and Ollama automatically |
| Node.js LTS / npm | Required, auto-installable with winget | Runtime for the Open Notebook frontend |
| SurrealDB CLI | Required, auto-installable with winget | Local Open Notebook database |
| Ollama | Required for the default local embedding setup, auto-installable with winget | Runs the `nomic-embed-text` embedding model locally |
| uv | Installed by the launcher if missing | Python package/environment manager used by this bundle |
| Internet access | Required for first setup | Download Python packages, npm modules, external tools, and Ollama models |

To install `winget`, get **App Installer** from the Microsoft Store or see the [winget documentation](https://learn.microsoft.com/en-us/windows/package-manager/). On a fresh Windows machine, a typical manual bootstrap is:

```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
```

> On a freshly installed system, install winget first, then run `OpenNotebookLM.bat`. The launcher will handle the remaining dependency checks automatically.

Docker Desktop is not required for the normal launcher path.

macOS and Linux users need Git, Python 3.11/3.12, Node.js/npm, SurrealDB CLI, Ollama, and `uv` installed through their system package manager or the upstream install instructions.

The launcher installs or repairs project-local dependencies with `uv` and `npm ci`. These are local to this checkout except for external tools such as Node.js, SurrealDB, Ollama, and `uv`.

On a fresh clone, the launcher prepares local runnable working copies from `components/opennotebook`, `components/notebooklm-py`, and `components/Hermes_agent`. Those root-level working copies are ignored by Git because they contain generated environments and runtime state.

Repeated launcher calls are safe. `OpenNotebookLM.bat` uses startup locks plus port probes so a second invocation waits for or reuses the existing Open Notebook backend/API on port `5055` and frontend on port `3000` instead of opening duplicate service windows.

## Quick start

```bat
git clone https://github.com/Car1sK/Codex-Notebook-Open.git
cd Codex-Notebook-Open
OpenNotebookLM.bat
```

Then open:

```text
http://localhost:3000
```

Useful commands:

```bat
OpenNotebookLM.bat --setup-only
OpenNotebookLM.bat --check
OpenNotebookLM.bat --check-live
OpenNotebookLM.bat --force-setup
OpenNotebookLM.bat --start-open-notebook
OpenNotebookLM.bat --setup-codex-mcp
OpenNotebookLM.bat --setup-hermes-mcp
OpenNotebookLM.bat --start-hermes
OpenNotebookLM.bat --stop-hermes
```

Use `--check` or `--check-install` for package/setup readiness checks that do not require live services. Use `--check-live` when you want to verify that the database, API, frontend, MCP bridges, and Hermes are currently running.

Only one root-level Windows batch file is shipped:

- `OpenNotebookLM.bat` — normal user entrypoint for setup, startup, checks, MCP refresh, and Hermes start/stop.

## Runtime data and secrets

Runtime data is intentionally local-only:

- `open-notebook-data/`
- `opennotebook/data/`
- `opennotebook/.env`
- `.venv/`
- `node_modules/`
- logs and temporary runtime artifacts

The launcher creates or repairs `opennotebook/.env` when needed. Do not commit encryption keys, passwords, notebook data, uploaded source material, or generated audio/text artifacts.

## Cloud multi-user deployment

For a public PaaS deployment, do not rely on the legacy single shared password if multiple people should manage separate notebooks. Configure named users with environment variables:

```env
OPEN_NOTEBOOK_ENCRYPTION_KEY=<stable encryption secret>
OPEN_NOTEBOOK_AUTH_SECRET=<stable random token signing secret>
OPEN_NOTEBOOK_USERS={"alice":"alice-password","bob":"bob-password"}
```

`OPEN_NOTEBOOK_USERS` also accepts comma-separated pairs:

```env
OPEN_NOTEBOOK_USERS=alice:alice-password,bob:bob-password
```

When `OPEN_NOTEBOOK_USERS` is set, the login page asks for both username and password. Each user receives a deterministic owner ID. User-owned notebooks, sources, notes, chat sessions, podcast episodes, embedding rebuilds, NotebookLM bundle mappings, relationship reads, search results, context building, downloads, audio streaming, and import/export paths are scoped to the logged-in owner. Global model credentials, model registry changes, settings, transformation templates, and podcast profile management remain restricted to the `default` administrator account.

Existing notebooks, sources, notes, chat sessions, podcast episodes, and NotebookLM sync mappings are assigned to the `default` owner by database migrations. To keep managing old data after enabling multi-user mode, include a `default` account in `OPEN_NOTEBOOK_USERS`, for example `{"default":"new-default-password","alice":"alice-password"}`. Otherwise export the old notebooks before switching from the legacy shared password.

For PaaS upgrades, keep the database volume and `OPEN_NOTEBOOK_ENCRYPTION_KEY` stable. Changing the encryption key can make already-saved encrypted credentials unreadable, and removing the persisted database volume removes the notebooks.

## Local embedding model

The default local embedding model checked by the launcher is:

```text
nomic-embed-text:latest
```

The stack check verifies that Ollama is reachable and returns a 768-dimensional embedding vector.

## License and attribution

The integration launcher and local glue code in this repository are released under the MIT License. Upstream bundled projects keep their own MIT licenses and copyright notices. See [THIRD_PARTY.md](THIRD_PARTY.md).

## Release packages

Release archives can be built locally. When publishing a GitHub Release, attach the generated files from `dist/`:

```bash
# --dry-run lists what would be included:
python scripts/build_release.py --dry-run

# Build zip and tar.gz:
python scripts/build_release.py --version 1.0.0
```

Output: `dist/Codex-Notebook-Open-<version>.zip` and `dist/Codex-Notebook-Open-<version>.tar.gz`.

The POSIX `.tar.gz` archive preserves the executable bit on `OpenNotebookLM.sh` so it's ready to run after extraction.

## Repository health check

Before publishing or handing the repository to another agent, run:

```bash
python scripts/check_repo_health.py
```

This validates README language links, obvious encoding damage, local/runtime Git exclusions, Python script syntax, and the release dry-run path.
