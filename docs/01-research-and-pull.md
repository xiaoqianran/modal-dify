# 01 — Dify 官方 Compose 与 Modal Sandbox 镜像下载研究

## 资料与可验证结果（2026-11-10）

- 旧仓库：`xiaoqianran/modal-mingdaoyun-skopeo-mirror`，已检查 README、app.py、mirror_ghcr.py、submit.py。
- 旧部署：`modal.Sandbox.create(... runtime="vm")`，运行 `dockerd`，通过 `sb.exec` 启动 Docker Compose；使用命名 Sandbox 复用、Modal Volume 挂载、encrypted_ports 创建隧道。旧代码设定 4 CPU、24 GiB、24 h 超时；这是旧配置，不是 Dify 实测值。
- Dify 官方：<https://github.com/langgenius/dify/tree/main/docker>。2026-11-10 读取 main/docker/docker-compose.yaml 时，解析到 41 个 image 服务引用、36 个不同镜像表达式，包含大量可选 profiles。**不要拉取全部 36 个**。
- 本次抓取的 main 中 api/web 为 1.19.0；正式项目必须固定官方 release/tag/commit，不要在生产中依赖浮动 main 或 latest。
- Docker 官方并发选项：<https://docs.docker.com/reference/cli/docker/compose/>；`docker compose --parallel 4 pull --policy missing`。
- CNB 环境已看到 Docker Compose v5.6.1、Modal client 1.6.3。尚未在 Modal VM 做拉取测速。

## 推荐实施顺序

1. 固定 Dify 官方 release tag 或 commit，并保留未改动的官方 Compose、依赖配置与对应的 .env.example；不要仅复制一个 yaml，漏掉 Nginx/Squid 等挂载文件。
2. 先运行 `docker compose config --quiet` 和 `docker compose config --images | sort -u`，确认启用的 services 和镜像。
3. 首轮只拉取默认部署实际启用的镜像：在 **Modal VM Sandbox 内** 测试 `--parallel 4`；脚本 `scripts/pull-images.sh` 可复用。记录冷启动及首次 pull 时长；改变并发度时必须区分已缓存的热拉取，避免结果失真。
4. 比较 2 / 4 / 8 路，记录每个镜像耗时、错误、总耗时及流量。过多并发会受限于磁盘 I/O、带宽与 Docker Hub 限额，不保证更快。
5. 将 Compose 和持久化目录放到适当的持久化方案。**Modal Volume 挂载应用数据不代表 Docker image layer 或 /var/lib/docker 自动持久**；VM 重建后镜像可能重新下载。先验证兼容性再选择镜像缓存、Volume/快照或者 GHCR 转存。
6. 数据库、Redis、上传文件和插件状态需要独立规划数据一致性与备份；Volume sync 不能替代 PostgreSQL 一致性备份。
7. 启动后验收 API / Web / worker / plugin_daemon / sandbox / vector DB 的健康与实际工作流。不要把容器 Up 当成可用。
8. Dify 自身的 `sandbox` 服务（代码执行容器）与 Modal VM Sandbox 是不同概念；重点验证容器隔离、network/SSRF、挂载、权限和插件执行兼容性。

## 默认资源和访问建议

- 从 4 vCPU / 16 GiB 作为**待测起点**，不是基于实测的最低配置；后续根据选用的数据库/向量库和峰值内存调整。下载压力和运行压力应分别评估。
- 优先只对外开放受保护的 Web 入口；数据库、Redis、plugin daemon、内部 sandbox 不直接公网暴露。
- 所有令牌与强密码放到 Modal Secrets 或本地忽略的 .env；不得提交真实值。

## 拉取基线命令

在已有 Docker Engine、官方 Dify Docker 目录和正确 .env 的环境中：

```bash
bash scripts/pull-images.sh /path/to/dify/docker 4
```

日志写在官方 docker 目录的 `pull-logs/`，不要提交日志中的敏感信息。

## 暂未完成

- 未实际拉取镜像，未得到网络速度/耗时。
- 未创建 Dify Modal Sandbox，未验证本次 Docker-in-Docker 容器兼容性。
- 未决策最终 pinned release 和持久化架构。
