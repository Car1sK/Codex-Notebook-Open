# Source snapshots

This repository bundles source snapshots of the runtime projects used by the local launcher under `components/`. The nested `.git` directories are not included in the public source bundle.

| Directory | Upstream | Snapshot commit |
|---|---|---|
| `components/Hermes_agent/` | https://github.com/NousResearch/hermes-agent | `3e7e9b24d40c6ff62e50936ba8b8184ad61da322` |
| `components/notebooklm-py/` | https://github.com/teng-lin/notebooklm-py | `0e92459c30925f6042e5597f5ec1bce014b9f969` |
| `components/opennotebook/` | https://github.com/lfnovo/open-notebook | `209b48cc104fdf56819206f428d9e801572cb992` |

Runtime data, secrets, virtual environments, `node_modules`, logs, generated HTML reports, large upstream test suites, recorded fixtures, documentation sites, and Hermes bundled skills are intentionally excluded.
