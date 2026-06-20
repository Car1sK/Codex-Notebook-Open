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
- Setup/check/start/stop helpers for Open Notebook, Ollama, Codex MCP, and Hermes
- Source snapshots of the three upstream runtime projects under `components/`
- Local MCP setup helpers for Codex and Hermes
- No local database, no secrets, no virtual environments, no `node_modules`, and no generated HTML reports

The bundled snapshots are trimmed for local runtime use. Large upstream test suites, recorded fixtures, documentation sites, generated reports, and Hermes bundled skills are not included.

## Requirements

- Windows 10/11
- Git
- PowerShell
- Internet access for first-run dependency installation
- `winget` is recommended so the launcher can install missing Node.js, SurrealDB, and Ollama

The launcher installs or repairs project-local dependencies with `uv` and `npm ci`. These are local to this checkout except for external tools such as Node.js, SurrealDB, Ollama, and `uv`.

On a fresh clone, the launcher prepares local runnable working copies from `components/opennotebook`, `components/notebooklm-py`, and `components/Hermes_agent`. Those root-level working copies are ignored by Git because they contain generated environments and runtime state.

## Quick start

```bat
git clone https://github.com/Alasyoki/Codex-Notebook-Open.git
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
OpenNotebookLM.bat --force-setup
start_open_notebook.bat
start_local_agent_stack.bat
start_ollama_models.bat
setup_codex_open_notebook_mcp.bat
setup_hermes_open_notebook_mcp.bat
start_hermes.bat
stop_hermes.bat
```

## Runtime data and secrets

Runtime data is intentionally local-only:

- `open-notebook-data/`
- `opennotebook/data/`
- `opennotebook/.env`
- `.venv/`
- `node_modules/`
- logs and delegation artifacts

The launcher creates or repairs `opennotebook/.env` when needed. Do not commit encryption keys, passwords, notebook data, uploaded source material, or generated audio/text artifacts.

## Local embedding model

The default local embedding model checked by the launcher is:

```text
nomic-embed-text:latest
```

The stack check verifies that Ollama is reachable and returns a 768-dimensional embedding vector.

## License and attribution

The integration launcher and local glue code in this repository are released under the MIT License. Upstream bundled projects keep their own MIT licenses and copyright notices. See [THIRD_PARTY.md](THIRD_PARTY.md).
