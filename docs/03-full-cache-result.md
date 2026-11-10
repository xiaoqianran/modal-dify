# 03 — Dify 1.19.0 全量镜像缓存构建与恢复实测

日期：2026-11-10。Modal 工作区由 CNB 已登录环境提供。

## 已执行（PASS）

- Dify 官方 GitHub release tag：`1.19.0`；固定 Git commit：`8e689e868b63b6dd2b449d0eb568ca5cc7127759`。
- 原样引入官方 `docker/` 子目录到 `vendor/dify-1.19.0/`，没有引入真实 `.env`。
- 使用官方默认 `COMPOSE_PROFILES=weaviate,postgresql,collaboration`。
- 运行 `docker compose config --images`，确认实际需要 12 个不同镜像引用。
- Modal VM：4 vCPU、16 GiB；下载任务并发数 4，Docker daemon max-concurrent-downloads 6。
- **12/12 镜像拉取并成功执行 image inspect**。
- 停止 Docker daemon，创建 `snapshot_filesystem(ttl=None)`。
- 发布正式 Named Image：`modal-dify-docker-cache-1-19-0`。
- Snapshot：`im-01M72269395ZZDPW99AZTFT12Z`。
- 缓存首次构建总耗时 111.9 秒，包含镜像准备、启动、下载、快照与发布。
- 构建 VM 已终止。
- 再用 `modal.Image.from_name` 创建新的 VM（2 vCPU、4 GiB），启动 Docker，逐一 inspect 12 镜像。
- **12/12 镜像 ID 与原始构建完全一致，未运行 docker pull，输出 RESULT=PASS**。
- 恢复验证 VM 已终止。

## 使用命令

```bash
python scripts/build_cache.py --plan
python scripts/build_cache.py --build
python scripts/verify_cache.py
```

构建命令调用真实计费云端资源，请勿无意重跑。

## 仍需完成

- 尚未启动 Dify 的 16 个默认 Compose 服务或测试浏览器页面。
- 仅验证了全部 12 个镜像的 Docker image inspect；尚未逐一启动全部容器。
- `nginx:latest`、`busybox:latest` 等官方浮动标签可能更新；当前 Named Image 中的具体 ID 已固定，但未来重新构建时应进一步锁定 digest。
- API/Web/Worker、插件、数据库、数据卷的实际健康检查、故障重建与一致性备份待测。
- Web 访问控制、SSRF 防护、密钥保管、数据库/文件备份必须在生产开放之前落实。
- 不应将缓存 Image 当成业务数据备份。
