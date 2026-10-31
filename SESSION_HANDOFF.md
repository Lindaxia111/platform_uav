# 会话交接摘要

更新时间：2026-10-31（Asia/Shanghai）。目录整理、开发规范和本次验证均已完成；恢复工作时按需核对实际文件。

## 项目与已完成工作

- 当前项目目录：`D:\platform`。
- 项目：多无人机系统建模与 AFSIM 验证工作台，第一版本地原型 0.1；Python/Tkinter 界面。
- 已从桌面原项目 `uav_workbench` 完整复制到当前目录，原目录保留。迁移时有 166 个文件，SHA-256 比对无缺失、额外文件或内容差异。
- 源项目没有 Git 仓库，因此没有迁移提交历史。
- 迁移后运行 22 项单元测试，全部通过；`python main.py check` 通过，仅有模型简化范围警告。核验后已恢复 `.test_runs` 为迁移时状态，并再次确认 166 个文件哈希一致。
- 已向用户解释平台启动、生成 A/B 比较、用 Mystic 查看回放和用 Wizard 查看场景的方法。此前尚未在迁移后的目录执行完整 AFSIM A/B 比较。
- 用户随后要求整理当前文件夹、优化结构，并明确要求后续开发按照规范约束执行。已增加开发规范、架构、AFSIM 操作说明和目录整理记录，通过 `AGENTS.md` 作为后续开发的必读约束。
- `demo_results/` 已移至 `examples/results/`（47 文件）；`.test_runs/` 已归档至 `artifacts/archive/test_runs_20261027/`（82 文件）。以上在移动时逐文件 SHA-256 校验一致；随后仅修复演示索引 `latest.json` 的导航路径，历史实验快照内容未改。
- 原 GUI 日志移至 `artifacts/logs/`；源码和测试中的旧 Python 缓存归档到 `artifacts/archive/python_cache_20261031/`。未删除历史文件。
- CLI 实现收拢到 `workbench/cli.py`，新增 `python -m workbench`，根 `main.py` 和原两个 CMD 启动入口保留。测试产物改写 `artifacts/test_runs/`，成功后清理，失败时保留。
- 新增 `.editorconfig`、`.gitattributes` 与统一检查入口 `scripts/verify.py` / `检查项目.cmd`，并更新 `.gitignore` 与 README。
- 整理后已执行 `python -X utf8 -B scripts/verify.py --with-afsim`：静态结构/语法/JSON/链接检查、22 项单元与隐藏界面测试、默认模型与引擎配置检查、旧 `main.py` 入口检查均通过；真实 AFSIM 的 `run_00`、`run_01` 都正常完成。
- 本次验证日志：`artifacts/verification/20261031_164124_5ad169f8/`；真实开发实验：`artifacts/runs/20261031_164128_4c19008b/`。覆盖率 A=82.333%、B=94.333%，两者仍未达到默认 95% 需求；这是运行完成而非需求达标，结果与既有示例一致。
- 成功测试的新用例产物已自动清理；82 个历史测试文件仍在归档目录。整理后检测到当前目录存在尚无提交的 Git 仓库（master），所有项目文件尚未跟踪；本次未创建提交。
- 已按用户要求创建首次提交 `3ac2f73`（`feat: initialize UAV algorithm validation workbench`），共 79 个文件，包括源码、启动与检查脚本、开发规范及已验证演示；本地产物、缓存和历史归档通过 `.gitignore` 排除。
- 用户指定 GitHub 仓库 `https://github.com/Lindaxia111/platform_uav.git`，已配置为 `origin`；关联前检查远程为空。当前开发分支为 `master`，远程目标为 `origin/master`。后续操作前使用 `git status --short --branch` 和 `git log -1` 核对提交与同步状态。
- 首次提交前补充 `.gitattributes`：`examples/results/** -text -whitespace`，保留历史证据及算法快照的原始字节，防止换行转换使快照哈希失配；只读证据豁免空白格式检查，开发源码继续检查。

## 启动与结果路径

- 平台：双击 `启动平台.cmd`，或在项目根目录执行 `python main.py gui`。
- AFSIM 安装根目录：`D:\afsim\afsim-2.9.0-win64`。
- 界面流程：“检查与执行” → 确认 AFSIM 目录 → “检查工程模型” → “生成场景并运行 A/B 比较”。结果页可打开预览和证据目录。
- 默认运行结果根目录：`%TEMP%\uav_workbench_runs`，每次运行有独立时间戳目录。
- `run_00` 为顺序轮询分配，`run_01` 为预计完成时间贪心分配。
- `mission.exe` 执行 `scenario.txt`；`mystic.exe` 打开 `replay.aer`；`wizard.exe` 打开 `scenario.txt`。这些程序位于 AFSIM 的 `bin` 目录。
- 已附演示结果：`examples\results\20261027_183740_6a6cec2a`，其中有 `preview.html`、两组场景和回放；`examples/results/latest.json` 的路径相对该索引文件。
- 默认工程：`examples\coverage_project.json`；历史验证记录：`docs/原型验证记录.md`；AFSIM 具体操作：`docs/AFSIM_GUIDE.md`。
- 结构与开发约束：`docs/ARCHITECTURE.md`、`docs/DEVELOPMENT.md`；迁移映射：`docs/STRUCTURE_CHANGELOG.md`。
- 统一验证：`python -X utf8 -B scripts/verify.py`；`--static-only` 只做静态检查；`--with-afsim` 追加真实 A/B 仿真。验证日志在 `artifacts/verification/`，开发仿真证据在 `artifacts/runs/`。

## 当前状态与后续协作

- 本次目录整理与规范落地已完成并通过上述验证；原有启动入口继续可用，历史证据和归档均保留。
- 用户最新偏好：会话很长时先总结，再开启新会话继续。已在 `AGENTS.md` 保存项目内的交接规则。
- 当前工具没有新建会话接口；不要声称已自动创建新会话或设置全局自动切换。需要用户在应用中新建会话，并发送：`继续 D:\platform 项目，请先读取 AGENTS.md 和 SESSION_HANDOFF.md。`
- 后续开发必须遵守 `AGENTS.md` 和 `docs/DEVELOPMENT.md`；当前无未完成修改，下一步等待用户的新功能需求。
