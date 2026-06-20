# Embedded repositories

This root repository is the private GitHub meta repo for the local OpenNotebookLM integration layer:

<https://github.com/Alasyoki/Codex-Notebook-Open>

The upstream project repositories remain independent Git repositories and are intentionally ignored by the root `.gitignore`.

| Directory | Remote | Current local commit |
|---|---|---|
| `Hermes_agent/` | https://github.com/NousResearch/hermes-agent.git | `3e7e9b24d40c6ff62e50936ba8b8184ad61da322` |
| `notebooklm-py/` | https://github.com/teng-lin/notebooklm-py.git | `0e92459c30925f6042e5597f5ec1bce014b9f969` |
| `opennotebook/` | https://github.com/lfnovo/open-notebook.git | `209b48cc104fdf56819206f428d9e801572cb992` |

Do not commit `.env`, `open-notebook-data/`, virtual environments, `node_modules/`, local logs, or delegation artifacts.
