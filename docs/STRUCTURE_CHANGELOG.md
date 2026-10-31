# 目录整理记录

日期：2026-10-31。

## 路径变化

| 原位置 | 当前位置 | 处理方式 |
|---|---|---|
| `demo_results/` | `examples/results/` | 47 个文件移动时逐项 SHA-256 校验一致；移动后仅导航索引 `latest.json` 改为相对路径 |
| `.test_runs/` | `artifacts/archive/test_runs_20261027/` | 82 个历史文件移动并逐项校验，保留诊断内容 |
| `gui_stdout.log`、`gui_stderr.log` | `artifacts/logs/` | 两个原始日志保留 |
| `原型验证记录.md` | `docs/原型验证记录.md` | 保留历史结果，更新预览与 README 链接 |
| 源码与测试中的旧 `__pycache__/` | `artifacts/archive/python_cache_20261031/` 下的原相对位置 | 保留归档，后续缓存由 Python 按需生成 |
| `main.py` 中的 CLI 逻辑 | `workbench/cli.py` | 根入口保留转发，新增 `python -m workbench` |

原有 `python main.py gui/check/compare`、`启动平台.cmd` 和 `一键验证.cmd` 继续可用。`一键验证.cmd` 执行的是默认 A/B 仿真；新增 `检查项目.cmd` 执行开发规范检查与测试。

## 持续约束

- 新增 [开发规范](DEVELOPMENT.md)、[架构说明](ARCHITECTURE.md) 与 [AFSIM 操作说明](AFSIM_GUIDE.md)，并通过根目录 `AGENTS.md` 作为后续开发入口。
- 新增 `.editorconfig` 和 `.gitattributes`；调整 `.gitignore`，忽略本地产物，并允许演示目录保留必要日志。
- 新增 `scripts/verify.py`，检查目录登记、必需文件、Python 语法、JSON、本地链接、已有测试和两个命令入口；可选执行真实 AFSIM A/B 比较。
- 测试新证据放在 `artifacts/test_runs/`，成功用例自动清理，失败保留；统一检查日志放在 `artifacts/verification/`。
- GUI 正常运行结果仍默认放在 `%TEMP%\uav_workbench_runs`，没有 `TEMP` 环境变量时回退到 `artifacts/runs/`。

实际执行的验证结果和最新状态以根目录 [会话交接摘要](../SESSION_HANDOFF.md) 为准。
