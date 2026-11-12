# 04 — Modal VM 上的 Dify 1.19.0 默认 Compose 测试部署

日期：2026-11-10。

## 已完成

- 使用发布的 Named Image `modal-dify-docker-cache-1-19-0` 创建新 VM。
- 在 VM 内安装 Docker Compose v2.40.3（满足 Dify 1.19.0 的最低要求）。
- 官方完整 `vendor/dify-1.19.0/docker-compose.yaml` 保持不改，默认 Profiles 维持 `weaviate,postgresql,collaboration`。
- 运行时在 VM 可写层生成 `.env`，敏感值不会写入 Named Image 或 Git。
- 部署脚本为 Nginx 增加 Basic Auth 访问层，不改 Dify 网页界面。
- 执行 `docker compose --parallel 4 up -d --pull never --no-build`，复用缓存的 12 个镜像。
- 15 个长期运行的服务均 Up，`init_permissions` 退出码为 0；API、PostgreSQL、Redis、Sandbox、Local Sandbox 的健康检查已通过。
- 外部测试：匿名 HTTPS 访问 /install 返回 401，Basic Auth 认证后返回 200。
- 实例：`modal-dify-vm` 下 `dify-119-evaluation`，4 CPU / 16 GiB，最长 24 h。
- HTTPS 入口：通过 `scripts/deploy.py status` 获取 Modal Tunnel 地址。

## 操作

在已登录 Modal 的 CNB 节点仓库目录：

```bash
/root/.local/share/uv/tools/modal/bin/python scripts/deploy.py status
/root/.local/share/uv/tools/modal/bin/python scripts/deploy.py credentials
/root/.local/share/uv/tools/modal/bin/python scripts/check_live.py
/root/.local/share/uv/tools/modal/bin/python scripts/deploy.py stop
```

`runtime/deploy-secrets.json` 包含本次部署的随机生成凭据，在 CNB 本地且被 Git 忽略。
请独立备份这些凭据。不要把它上传 GitHub，也不要把业务密码写入镜像缓存。
`start` 对正在运行的同名 VM 采取复用，不会重新部署。

## 重大限制

**仅测试部署，尚无跨 VM 的业务数据持久化恢复保证。**

目前 PostgreSQL、Redis、Weaviate、插件、上传文件的 Docker bind-mount 数据均写在
本次 VM 的本地可写层。VM 到期或被销毁会丢失这些数据。请勿用于长期保存的实际业务。
即使 Named Image 能恢复 Docker 镜像，也不会恢复这些业务数据。

下一步必须设计并实测外部可靠存储（对象存储、数据库）或者一致性数据库备份以及按计划的自动恢复；
且必须做强制销毁 VM 后的真实恢复验收。
当前入口 Basic Auth 仅保护访问，不能替代 Dify 账号、安全审核和备份策略。
Docker 引擎的主机端口仅有 Modal encrypted_ports=[80] 暴露在 Tunnel，内部端口不应额外公开。

当前 Sandbox 最长 86400s，运行期间会持续产生 Modal 费用；Named Image 自身无需持续 VM 计算。

## MCP 接入（与 Dify 同生命周期）

官方 Compose 已有 `/mcp` 到 `api:5001` 的转发。`scripts/deploy.py` 在新 VM 的可写层为原生 MCP 工具调用端点取消 Nginx Basic Auth，其他路由保持全站 Basic Auth；Modal Tunnel 仍只暴露 80 端口，不增加容器或额外公网服务。

1. 通过 `scripts/deploy.py start` 启动新评估实例；`status` 查看 `DIFY_URL` 与 `MCP_URL_FORMAT`。
2. 登录 Dify，发布工作流，开启该应用的 MCP Server，并复制 Dify 提供的实际 MCP URL。
3. 在 CNB AgentDock 的动态 MCP 配置中使用该 URL，传输协议选择 Streamable HTTP。
4. 验证 `initialize`、`tools/list` 和一次无敏感副作用的 `tools/call`。

**安全约束：** 精确的 `/mcp/server/<server_code>/mcp` 路径无需额外 Basic Auth，但 Dify 生成的 server code 是访问凭据；任何持有该链接的人都可能调用暴露的工具。勿公开链接或授权高危工具。其余路径依然要求 Basic Auth。此改动只应用于新创建的 VM；已经启动且由 `start` 复用的 VM 不会被覆盖。

**生命周期：** VM 停止后 MCP 同时失效；新 VM 的 Tunnel URL 可能变化，需要同步更新 AgentDock。当前不具备跨 VM 数据持久化保证，尚未执行真实 MCP 端到端验收。

## 插件存储目录权限

`plugin_daemon` 容器以 UID/GID `1001:1001` 运行，并将宿主 `volumes/plugin_daemon` 绑定到 `/app/storage`。Docker 自动创建缺失目录时可能采用 `root:root`、`755`，使插件安装无法创建 `/app/storage/assets`。部署脚本在启动 Compose 前创建该目录并设为 `1001:1001`；不需要 `777`，也不递归更改已有插件文件属主。

## 默认内存调整（2026-11-12）

新建 Modal Sandbox VM 的默认内存从 16 GiB 改为 8 GiB，CPU 仍为 4 vCPU。
修改仅影响新创建的 VM；`start` 复用已运行实例时不会调整其规格。
现有实例包含用户注册信息、工作流及插件配置，**不得为调整内存直接销毁**，
除非先完成并验证数据备份及迁移恢复。8 GiB 能否承载实际负载仍需新实例实测。
