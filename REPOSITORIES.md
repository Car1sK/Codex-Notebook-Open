# Embedded repositories

This root repository is a meta repo for the local OpenNotebookLM integration layer. The upstream project repositories remain independent Git repositories and are intentionally ignored by the root `.gitignore`.

| Directory | Remote | Current local commit |
|---|---|---|
| $(@{Name=Hermes_agent; Remote=https://github.com/NousResearch/hermes-agent.git; Commit=3e7e9b24d40c6ff62e50936ba8b8184ad61da322}.Name)/ | https://github.com/NousResearch/hermes-agent.git | $(@{Name=Hermes_agent; Remote=https://github.com/NousResearch/hermes-agent.git; Commit=3e7e9b24d40c6ff62e50936ba8b8184ad61da322}.Commit) |
| $(@{Name=notebooklm-py; Remote=https://github.com/teng-lin/notebooklm-py.git; Commit=0e92459c30925f6042e5597f5ec1bce014b9f969}.Name)/ | https://github.com/teng-lin/notebooklm-py.git | $(@{Name=notebooklm-py; Remote=https://github.com/teng-lin/notebooklm-py.git; Commit=0e92459c30925f6042e5597f5ec1bce014b9f969}.Commit) |
| $(@{Name=opennotebook; Remote=https://github.com/lfnovo/open-notebook.git; Commit=209b48cc104fdf56819206f428d9e801572cb992}.Name)/ | https://github.com/lfnovo/open-notebook.git | $(@{Name=opennotebook; Remote=https://github.com/lfnovo/open-notebook.git; Commit=209b48cc104fdf56819206f428d9e801572cb992}.Commit) |

Do not commit `.env`, `open-notebook-data/`, virtual environments, `node_modules/`, local logs, or delegation artifacts.
