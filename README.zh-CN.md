# Codex Notebook Open

[English](README.md) | 中文

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

## 快速开始（macOS / Linux）

```bash
git clone https://github.com/Alasyoki/Codex-Notebook-Open.git
cd Codex-Notebook-Open
./OpenNotebookLM.sh
```

然后打开 `http://localhost:3000`。

POSIX 启动器支持与 Windows .bat 相同的模式：

```bash
./OpenNotebookLM.sh --setup-only
./OpenNotebookLM.sh --check
./OpenNotebookLM.sh --check-live
./OpenNotebookLM.sh --stop
./OpenNotebookLM.sh --help
```

Windows 用户请使用 `OpenNotebookLM.bat`（参见下方说明）。

## 环境要求

- Windows 10/11、macOS 或 Linux
- 所有平台都需要 Python 3.8+。Windows 用户可以使用 Python 启动器 `py -3`。
- Git
- 首次安装需要联网
- Windows 推荐安装 `winget`，这样启动器可以自动安装缺失的 Node.js、SurrealDB、Ollama

启动器会用 `uv` 和 `npm ci` 安装或修复项目本地依赖。除了 Node.js、SurrealDB、Ollama、`uv` 这类外部工具外，依赖会放在当前仓库 checkout 内。

新克隆仓库首次启动时，启动器会从 `components/opennotebook`、`components/notebooklm-py`、`components/Hermes_agent` 复制出根目录运行副本。根目录运行副本会被 Git 忽略，因为里面会生成虚拟环境和运行状态。

重复调用启动器是安全的。`OpenNotebookLM.bat` 和 `start_open_notebook.bat` 会使用启动锁和端口探测；第二次调用会等待或复用已有的 Open Notebook 后端/API（端口 `5055`）和前端（端口 `3000`），不会再打开重复的服务窗口。

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
OpenNotebookLM.bat --check-live
OpenNotebookLM.bat --force-setup
start_open_notebook.bat
start_local_agent_stack.bat
start_ollama_models.bat
setup_codex_open_notebook_mcp.bat
setup_hermes_open_notebook_mcp.bat
start_hermes.bat
stop_hermes.bat
```

`--check` 或 `--check-install` 用于检查发布包/安装准备状态，不要求服务已经运行。需要确认数据库、API、前端、MCP 桥接和 Hermes 当前正在运行时，使用 `--check-live`。

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

## 发布包

发布包可以在本地构建。发布 GitHub Release 时，将 `dist/` 中生成的文件作为附件上传：

```bash
# --dry-run 列出将包含的文件：
python scripts/build_release.py --dry-run

# 构建 zip 和 tar.gz：
python scripts/build_release.py --version 1.0.0
```

输出：`dist/Codex-Notebook-Open-<version>.zip` 和 `dist/Codex-Notebook-Open-<version>.tar.gz`。

POSIX `.tar.gz` 归档保留了 `OpenNotebookLM.sh` 的可执行位，解压后即可运行。

## 仓库健康检查

发布或交给其他代理前，运行：

```bash
python scripts/check_repo_health.py
```

它会检查 README 语言链接、明显编码损坏、本地运行数据的 Git 排除规则、Python 脚本语法，以及发布包 dry-run 路径。
