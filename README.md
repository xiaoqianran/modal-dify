# modal-dify

使用 Modal Sandbox + Docker Compose 部署自托管 Dify。

当前状态：仓库初始化，部署方案待实现。

## 当前进度

- [镜像并发拉取研究](docs/01-research-and-pull.md)
- [Modal VM Docker 缓存架构与最小跨 VM 实测（PASS）](docs/02-cache-architecture.md)
- [最小快照验证脚本](scripts/test_vm_image_snapshot.py)（仅小镜像；不部署 Dify；自动清理 VM）

**尚未部署 Dify 正式服务**；12 镜像完整快照、业务数据持久化与应用验证待完成。
