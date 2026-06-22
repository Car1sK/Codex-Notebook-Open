# PaaS 上的 Open Notebook 多用户迁移教程：保留已有 notebook

本文适用于已经把本项目部署到 PaaS，并且已经有旧 notebook 数据的用户。目标是把旧的“单一共享密码”模式切换为“多人账号登录，各自管理自己的云端 notebook”的模式，同时保留原有 notebook。

这里的“notebook 文件”通常不是一个普通 `.md` 或 `.ipynb` 文件，而是 Open Notebook 保存在数据库和持久化存储里的数据，包括：

- notebook 记录
- sources / 上传资料 / 解析文本
- notes
- chat sessions
- podcast episodes
- NotebookLM 同步映射
- 已保存的模型凭据等加密配置

所以保留旧 notebook 的核心不是复制某个单独文件，而是保留数据库持久化卷、上传文件存储，以及原来的加密密钥。

## 一、迁移前先确认三件事

### 1. 确认 PaaS 使用的是持久化数据库

不要让数据库存在临时容器文件系统里。你需要确认 SurrealDB / Open Notebook 数据目录挂载到了 PaaS 的持久化卷。

如果你的 PaaS 有“Volume”“Persistent Disk”“Storage”“Mount Path”之类配置，确保 Open Notebook 的数据库目录和上传文件目录在持久化卷内。

如果没有持久化卷，重新部署、重启或换镜像后可能会丢失 notebook。

### 2. 记录当前的加密密钥

必须保留原来的：

```env
OPEN_NOTEBOOK_ENCRYPTION_KEY
```

不要重新生成，不要删除，不要换值。

这个密钥用于读取已保存的加密配置，例如模型 API key / provider 凭据。更换后，旧加密内容可能无法解密。

### 3. 备份数据库和上传文件

迁移前请在 PaaS 控制台做一次备份。最低要求：

- 备份数据库持久化卷
- 备份上传文件/运行数据持久化卷
- 记录当前所有环境变量

如果 PaaS 支持快照，优先使用快照。

## 二、更新到支持多用户的新版代码

将 PaaS 部署源更新到当前仓库最新 `main` 分支：

```text
https://github.com/Car1sK/Codex-Notebook-Open
```

如果你的 PaaS 是从 GitHub 自动部署：

1. 进入 PaaS 项目设置。
2. 确认仓库指向 `Car1sK/Codex-Notebook-Open`。
3. 确认分支是 `main`。
4. 触发一次重新部署。

如果你的 PaaS 是手动上传镜像或压缩包，则需要重新构建并上传包含最新代码的版本。

## 三、配置多用户环境变量

### 必填变量

在 PaaS 的环境变量中设置：

```env
OPEN_NOTEBOOK_ENCRYPTION_KEY=<保持原来的稳定加密密钥>
OPEN_NOTEBOOK_AUTH_SECRET=<新建一个稳定的随机 token 签名密钥>
OPEN_NOTEBOOK_USERS={"default":"管理员密码","alice":"alice密码","bob":"bob密码"}
```

说明：

- `OPEN_NOTEBOOK_ENCRYPTION_KEY`：必须沿用旧值，用来保留旧数据的可读性。
- `OPEN_NOTEBOOK_AUTH_SECRET`：用于签发登录 token。设置后不要频繁更换，否则所有用户需要重新登录。
- `OPEN_NOTEBOOK_USERS`：开启多用户模式。只要这个变量存在并且能解析出用户，就不再使用旧的单一共享密码登录。

### 为什么必须保留 `default` 用户

旧数据会通过数据库迁移归属到：

```text
default
```

因此，如果你想继续看到并管理原来的 notebook，必须在 `OPEN_NOTEBOOK_USERS` 里加入 `default` 账号。

示例：

```env
OPEN_NOTEBOOK_USERS={"default":"my-admin-password","alice":"alice-password","bob":"bob-password"}
```

迁移后：

- 用 `default` 登录：可以看到旧 notebook。
- 用 `alice` 登录：只能看到 alice 自己创建的 notebook。
- 用 `bob` 登录：只能看到 bob 自己创建的 notebook。

### 逗号分隔格式

如果你的 PaaS 不方便填写 JSON，也可以用逗号格式：

```env
OPEN_NOTEBOOK_USERS=default:my-admin-password,alice:alice-password,bob:bob-password
```

但更推荐 JSON，因为密码里如果包含逗号或冒号，逗号格式容易出错。

## 四、旧变量如何处理

如果之前使用的是单一共享密码：

```env
OPEN_NOTEBOOK_PASSWORD=<旧共享密码>
```

启用 `OPEN_NOTEBOOK_USERS` 后，多用户登录会优先生效，旧共享密码不会再作为普通 bearer 密码通过认证。

建议：

- 可以保留 `OPEN_NOTEBOOK_PASSWORD` 作为历史记录，但不要依赖它登录。
- 更干净的方式是删除 `OPEN_NOTEBOOK_PASSWORD`，只保留 `OPEN_NOTEBOOK_USERS`。
- 不要删除 `OPEN_NOTEBOOK_ENCRYPTION_KEY`。

## 五、部署时会发生什么

新版服务启动后会自动运行数据库迁移。

关键迁移效果：

- 给 notebook / source / note / chat session 加 owner 字段。
- 给 podcast episode 加 owner 字段。
- 给 NotebookLM 同步映射加 owner 字段。
- 将没有 owner 的旧数据归属到 `default`。

这些迁移不会删除旧 notebook。

注意：迁移依赖原数据库仍然存在。如果你换了空数据库或删了持久化卷，迁移也无法恢复已经丢失的数据。

## 六、部署后的验证流程

部署完成后，按下面顺序验证。

### 1. 打开登录页

访问你的 PaaS 地址，例如：

```text
https://你的域名/notebooks
```

如果已经配置 `OPEN_NOTEBOOK_USERS`，登录页应该出现：

- 用户名
- 密码

如果只看到密码输入框，说明多用户变量没有生效，需要检查 `OPEN_NOTEBOOK_USERS`。

### 2. 用 `default` 登录

使用：

```text
用户名：default
密码：你在 OPEN_NOTEBOOK_USERS 里设置的 default 密码
```

确认：

- 能进入系统。
- 能看到原来的 notebook。
- 原来的 sources / notes 仍然存在。
- 原来需要的模型配置仍可使用。

如果看不到旧 notebook，优先检查：

- 是否连接到了原来的数据库持久化卷。
- 是否保留了原来的数据库数据。
- 是否真的包含 `default` 用户。
- 是否部署到了最新代码。

### 3. 用普通用户登录并创建测试 notebook

例如用 `alice` 登录。

创建一个测试 notebook：

```text
Alice Test Notebook
```

确认：

- alice 能看到自己创建的 notebook。
- alice 看不到 `default` 的旧 notebook。

### 4. 用另一个用户登录验证隔离

退出 alice，改用 bob 登录。

确认：

- bob 看不到 alice 创建的 `Alice Test Notebook`。
- bob 可以创建自己的 notebook。
- bob 看不到 default 的旧 notebook。

### 5. 验证管理员边界

全局配置类操作只应该由 `default` 管理员执行，包括：

- 模型凭据
- 模型注册表修改
- 全局 settings 修改
- transformation 模板管理
- podcast profile 管理

普通用户主要管理自己的：

- notebooks
- sources
- notes
- chats
- podcast episodes
- imports / exports

## 七、常见问题

### Q1：我用 alice 登录后旧 notebook 不见了，是不是丢了？

通常不是。

旧 notebook 会归属到 `default` 用户。请用 `default` 登录查看。

如果 `default` 也看不到，再检查数据库持久化卷是否正确挂载。

### Q2：我能不能把旧 notebook 分配给 alice？

当前默认迁移策略是把旧数据归到 `default`，保证不丢数据。

如果你要把某些旧 notebook 转给 alice，需要额外写一次受控迁移脚本，按 notebook/source/note/chat session 的 owner 一起迁移。不要只改 notebook 一张表，否则关联数据可能仍留在 default 下。

### Q3：我可以更换 `OPEN_NOTEBOOK_AUTH_SECRET` 吗？

可以，但更换后所有已登录用户的 token 会失效，需要重新登录。

这不会删除 notebook。

### Q4：我可以更换 `OPEN_NOTEBOOK_ENCRYPTION_KEY` 吗？

不建议。

更换后可能导致已保存的加密凭据无法读取。为了保留旧配置，请保持原值。

### Q5：旧的 `OPEN_NOTEBOOK_PASSWORD` 还需要吗？

多用户模式下不需要。

设置 `OPEN_NOTEBOOK_USERS` 后，登录改为用户名 + 密码。旧共享密码不再作为多人云端部署的主要认证方式。

### Q6：删除某个用户会怎样？

如果你从 `OPEN_NOTEBOOK_USERS` 中删除某个用户名：

- 该用户无法再登录。
- 该用户已有 token 会被拒绝。
- 该用户的数据不会自动删除。

如果后续重新加入相同用户名，因为 owner ID 是按用户名稳定生成的，该用户通常还能看到原来属于自己的数据。

### Q7：用户名大小写要注意吗？

owner ID 会按用户名的小写形式派生。建议只使用小写用户名，例如：

```text
default
alice
bob
```

不要混用 `Alice` 和 `alice`。

## 八、推荐上线步骤清单

按顺序执行：

1. 在 PaaS 上备份数据库和上传文件持久化卷。
2. 记录当前所有环境变量，特别是 `OPEN_NOTEBOOK_ENCRYPTION_KEY`。
3. 更新 PaaS 部署源到最新 `main` 分支。
4. 设置：

   ```env
   OPEN_NOTEBOOK_ENCRYPTION_KEY=<旧值>
   OPEN_NOTEBOOK_AUTH_SECRET=<稳定随机新值>
   OPEN_NOTEBOOK_USERS={"default":"管理员密码","alice":"alice密码","bob":"bob密码"}
   ```

5. 确认数据库持久化卷没有被换成新的空卷。
6. 重新部署。
7. 用 `default` 登录，确认旧 notebook 存在。
8. 用 alice 创建测试 notebook。
9. 用 bob 登录，确认看不到 alice 的 notebook。
10. 保留备份一段时间，确认生产使用无异常后再清理旧备份。

## 九、回滚建议

如果部署后发现问题，优先回滚代码版本和环境变量，但不要删除数据库卷。

推荐回滚顺序：

1. 保留当前数据库卷，不要重置。
2. 回滚 PaaS 部署到旧镜像/旧提交。
3. 恢复旧环境变量。
4. 如果数据库迁移后的 schema 与旧版本不兼容，再使用迁移前的数据库备份恢复。

最安全的策略是：迁移前一定要做数据库快照。

