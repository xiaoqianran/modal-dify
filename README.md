# modal-dify

使用 Modal Sandbox + Docker Compose 部署自托管 Dify。

当前状态：仓库初始化，部署方案待实现。

## 当前进度

- [镜像并发拉取研究](docs/01-research-and-pull.md)
- [Modal VM Docker 缓存架构与最小跨 VM 实测（PASS）](docs/02-cache-architecture.md)
- [最小快照验证脚本](scripts/test_vm_image_snapshot.py)（仅小镜像；不部署 Dify；自动清理 VM）

**尚未部署 Dify 正式服务**；12 镜像完整快照、业务数据持久化与应用验证待完成。

## 全量缓存已验证（2026-11-10）

Dify 官方 `1.19.0` 的 12/12 默认镜像已并发拉取、生成持久快照并发布为
`modal-dify-docker-cache-1-19-0`。从 Named Image 创建新 VM 后，
12/12 镜像无需重新下载即可通过 `docker image inspect`，验证结果 PASS。

- [完整实测记录](docs/03-full-cache-result.md)
- [缓存构建脚本](scripts/build_cache.py)
- [缓存恢复验证脚本](scripts/verify_cache.py)

下一步是部署官方默认 Compose 服务，并专门实现数据库和上传数据的可靠持久化与恢复。

## 原生 MCP 公网接入

Dify 自带 MCP Server，无需 MCP Gateway、额外容器或第二个 Modal Sandbox。现有 Nginx 负责 Web/API 路由，Modal `encrypted_ports=[80]` 负责公网 HTTPS。

启动并查看当前入口（在配置好 Modal 的环境中）：

```bash
python scripts/deploy.py start
python scripts/deploy.py status
```

输出包含 `DIFY_URL` 和 `MCP_URL_FORMAT`。先登录 Dify 发布工作流并启用 MCP Server，然后用 Dify 实际提供的完整 URL（包含独有的 server code）在 AgentDock 中注册 Streamable HTTP MCP 服务。不能将 `MCP_URL_FORMAT` 中的占位符直接作为可用连接。

部署脚本仅对 `/mcp/server/<server_code>/mcp`（及尾随 `/`）取消额外的 Nginx Basic Auth；Dify 管理界面及其他路由继续使用 Basic Auth。**MCP server code 相当于访问凭据**，不要公开分享、写入 Git 或日志。使用最小权限的测试工作流，避免开放敏感操作。

当前仍是非持久化的评估部署：VM 到期或销毁后业务数据可能丢失，Tunnel 地址可能改变。重新启动后需更新 AgentDock 配置。更详细的限制见 [测试部署说明](docs/04-evaluation-deploy.md)。
