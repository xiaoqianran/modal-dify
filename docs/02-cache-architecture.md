# 02 — Modal VM Docker 镜像缓存架构审查与实测

审查日期：2026-11-10。

## 结论

**通过最小实测**：VM Sandbox（Debian + Docker Engine）的 `/var/lib/docker` 镜像层可通过
`Sandbox.snapshot_filesystem()` 保存为 Modal Image，在销毁原 VM、从快照创建新 VM
后，仍然能够离线 inspect 和 run。此结论严格限于已测试配置，不等于全量 Dify 服务验证。

## 真实实验

脚本：`scripts/test_vm_image_snapshot.py`。
Modal 工作区：当前 CNB 已登录的工作区，测试未使用用户密钥和业务数据。
资源：每台 VM 2 CPU / 4 GiB，最多两台先后创建，不对外开放端口。
基础镜像：`modal.Image.debian_slim(python_version="3.12").apt_install("docker.io", "iptables", "procps")`。
运行时：`runtime="vm"`。

步骤：
1. 创建 VM，独立启动 dockerd。
2. 拉取 `busybox:1.37.0` 与 `redis:6-alpine`。
3. 记录 Docker 镜像 ID，安全停止 dockerd。
4. `sb.snapshot_filesystem(timeout=300, ttl=3600)`，生成临时快照。
5. 终止原 VM；使用这个快照作为 Image 创建第二台 VM。
6. 重启 dockerd，检查 Docker 镜像 ID 一致。
7. `docker run --pull=never --rm busybox:1.37.0 echo CACHE_OK` 成功。
8. 终止第二台 VM。

测试记录：
- `busybox:1.37.0` pull 1.86 秒
- `redis:6-alpine` pull 1.50 秒
- snapshot 1.27 秒
- 整体 38.13 秒（含 Modal VM 创建与恢复）
- 结果：`RESULT=PASS`
- Docker image ID：
  - busybox: `sha256:30ecbe1509090b38ef3260f3609d64d8261230464eaa4d235901db496e9647fb`
  - redis: `sha256:7591c8f8a3f00d7fb5ea8a660407c21103b7516d1d3b4cf32774a3b090d91017`
- Snapshot ID：`im-01M721HGG5YP6M7EVATQ2W76CT`（仅 1h 临时有效，**不是长期缓存**）。
- 测试 VM 已停止。

第一次尝试 `modal.Image.from_registry("docker:28-dind")` 在当前账号旧版 Modal Image Builder 中失败，
原因是导入该镜像时 Builder 执行 `python -m pip`，而 docker:dind 无 Python；
此失败发生于基础镜像构建、**不是 Docker 快照/恢复失败**。改成 Debian + Docker 成功。

## 目标架构（待全量验证）

```text
版本固定的官方 Dify Compose + .env.example
                  |
                  v
     一次性 Cache Builder VM
     - Docker Engine
     - compose config --images 校验
     - 并发拉取官方默认实际使用的 12 个镜像
     - docker image inspect/manifest 验证
     - 停止 dockerd
                  |
                  v
    snapshot_filesystem(ttl=None)
                  |
                  v
  publish('modal-dify-docker-cache:<pinned-version>')
                  |
                  v
     Dify VM from named Image
     - Docker Engine
     - Compose Up --pull never
     - 数据/密钥在运行期单独加载
```

- 只对缓存预热 VM 制作镜像快照；不要把持续变化的业务数据库快照当做长期缓存。
- 创建 Named Image 前必须确保 Docker 已停止，并且镜像 ID、清单和配置版本可追踪。
- 缓存快照仅包含 Docker 镜像与必要配置，**禁止包含实际 Dify .env、Token、密码、数据库内容**。
- 如果某次版本更新失败，新 VM 应继续采用上一版 Named Image，不应自动回退到线上 pull 未验证镜像。
- 若全量 12 镜像快照失败，回退为 Modal Volume/R2 保存 `docker save` 归档、
  新 VM 用 `docker load` 恢复（较慢，但避免逐镜像从上游拉取）。此回退未实测。
- 对比不同并发度时应在相同的冷缓存条件下测试，否则受到 Docker layer cache 污染。
- 通过 `docker compose --parallel 4 pull --policy missing` 预热当前启用镜像；
  仅在缓存完整时 `docker compose up -d --pull never`。

## 业务数据和启动注意

- 运行前校验官方 Dify 版本固定，Compose 所需的 bind-mount 文件齐全。
- PostgreSQL、Redis、向量数据库、插件状态、上传文件等需要**独立**设计存储和恢复；
  单纯使用 Modal Volume 不等于数据库事务一致性备份；不能把 `/var/lib/docker`
  直接挂载 Volume 并假定 overlay2 行为可靠。
- 生产场景优先考虑外部托管 PostgreSQL/Redis 和可靠的对象存储/备份。
  如果必须维持全部本机 Compose 状态服务，应先证明数据库写入、Volume commit、重建恢复、恢复点校验。
- 只公开有访问控制的 Web 入口；不可直接开放 DB/Redis/管理接口。
- 大体量镜像 Snapshot 的耗时和存储费用尚未测量。
- 默认 16 个 active services、12 个 distinct images 来自 2026-11-10 官方 main
  的 `docker compose config`，并非永远固定的数字；升级后要重新检查。

## 官方参考

- <https://modal.com/docs/sdk/py/latest/Sandbox>
- <https://modal.com/docs/reference/modal.Image>
- <https://modal.com/blog/vm-sandboxes-agent-computers>
- <https://modal.com/docs/sdk/py/latest/Volume>
- <https://github.com/langgenius/dify/tree/main/docker>
