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
