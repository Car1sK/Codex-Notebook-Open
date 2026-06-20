# OpenNotebookLM Local Stack

Root meta repository for the local Open Notebook + notebooklm-py + Hermes integration layer.

Normal user entrypoint:

```bat
OpenNotebookLM.bat
```

Useful maintenance commands:

```bat
OpenNotebookLM.bat --setup-only
OpenNotebookLM.bat --check
OpenNotebookLM.bat --force-setup
```

This repository tracks only the integration layer: launchers, helper scripts, operator docs, and workspace guidance.

The upstream project folders are intentionally kept as independent repositories and are not tracked here:

- `Hermes_agent/`
- `notebooklm-py/`
- `opennotebook/`

See `REPOSITORIES.md` for their remotes and current local commit pins.

Never commit local secrets, runtime data, virtual environments, `node_modules`, logs, or Open Notebook database files.
