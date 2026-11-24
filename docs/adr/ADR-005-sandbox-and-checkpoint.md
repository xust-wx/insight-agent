# ADR-005 · 代码沙箱加固与状态持久化方案

- 状态：已接受（2026-11-24）
- 关联评审项：`S0_review.md` P1-3、P2-3、P2-11

## 决策 1：预热常驻加固 Docker 沙箱 + 预置拆解算法库
- **放弃每步 `docker run` 冷启动**（Windows Docker Desktop 每次起容器约耗 1.5~3s），改为在 `docker-compose.yml` 中启动常驻受限容器 `insight-sandbox-worker`，通过 `docker exec` 在独立子目录 `/workspace/<thread_id>/<run_id>` 执行，超时 30s 强杀进程。
- **安全加固**：`--network none`、`--read-only`、`--tmpfs /tmp:rw,noexec,nosuid,size=64m`、`-e MPLCONFIGDIR=/tmp/matplotlib`（解决只读根文件系统下 `matplotlib` 缓存写入失败问题）、`--cap-drop ALL`、`--security-opt no-new-privileges:true`、`--pids-limit 64`、非 root 用户（`65534:65534`）。
- **算法内聚**：将确定性拆解库 `insight_sandbox_lib`（加法贡献、LMDI、PVM 结构效应、异常检测）直接打包进沙箱镜像，模型只写薄胶水代码调用标准函数并输出结构化 JSON，消除现场手写公式算错的风险。

## 决策 2：复用 PostgreSQL 独立 Schema 做 Checkpointer
- 选用 `langgraph-checkpoint-postgres`（`AsyncPostgresSaver`），存储在同一 PostgreSQL 实例的独立 Schema `agent_state` 中。
- 业务只读账号 `readonly_analyst` 对 `agent_state` 无任何访问权限，实现业务数据与运行时状态隔离，同时避免再引入额外数据库组件。
