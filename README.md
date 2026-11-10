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
