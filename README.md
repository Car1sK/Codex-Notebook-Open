# Codex Notebook Open

English | [中文](#中文)

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

---

## 中文

Codex Notebook Open 是一个面向 Windows 本地环境的一键启动与集成项目，整合：

- [Open Notebook](https://github.com/lfnovo/open-notebook)
- [notebooklm-py](https://github.com/teng-lin/notebooklm-py)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent)
- [Ollama](https://ollama.com/) 本地 embedding

目标是提供一个可直接运行的本地笔记与代理协作环境：用户在 Open Notebook 网页界面里管理资料、笔记本和最终笔记；Codex 与 Hermes 通过本地 notebooklm-py CLI/MCP 桥接进行受控自动化。

## 包含内容

- Windows 一键入口：`OpenNotebookLM.bat`
- Open Notebook、Ollama、Codex MCP、Hermes 的安装/检查/启动/停止脚本
- `components/` 下的三个上游运行项目源码快照
- Codex 与 Hermes 的本地 MCP 配置辅助脚本
- 不包含本地数据库、密钥、虚拟环境、`node_modules`、生成的 HTML 报告

打包快照按本地运行用途裁剪，不包含大型上游测试集、录制夹具、文档站点、生成报告，以及 Hermes 自带 skills。

## 环境要求

- Windows 10/11
- Git
- PowerShell
- 首次安装需要联网
- 推荐安装 `winget`，这样启动器可以自动安装缺失的 Node.js、SurrealDB、Ollama

启动器会用 `uv` 和 `npm ci` 安装或修复项目本地依赖。除了 Node.js、SurrealDB、Ollama、`uv` 这类外部工具外，依赖会放在当前仓库 checkout 内。

新克隆仓库首次启动时，启动器会从 `components/opennotebook`、`components/notebooklm-py`、`components/Hermes_agent` 复制出根目录运行副本。根目录运行副本会被 Git 忽略，因为里面会生成虚拟环境和运行状态。

## 快速开始

```bat
git clone https://github.com/Alasyoki/Codex-Notebook-Open.git
cd Codex-Notebook-Open
OpenNotebookLM.bat
```

然后打开：

```text
http://localhost:3000
```

常用命令：

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

## 运行数据和密钥

以下内容只保留在本地，不进入仓库：

- `open-notebook-data/`
- `opennotebook/data/`
- `opennotebook/.env`
- `.venv/`
- `node_modules/`
- 日志和 Hermes 委派产物

启动器会在需要时创建或修复 `opennotebook/.env`。不要提交加密密钥、密码、笔记数据库、上传资料或生成的音频/文本产物。

## 本地 embedding 模型

默认检查的 Ollama 本地 embedding 模型是：

```text
nomic-embed-text:latest
```

栈检查会确认 Ollama 可访问，并返回 768 维 embedding 向量。

## 许可证与引用

本仓库中的集成启动器和本地胶水代码使用 MIT License。打包的上游项目保留各自的 MIT License 和版权声明。详见 [THIRD_PARTY.md](THIRD_PARTY.md)。
