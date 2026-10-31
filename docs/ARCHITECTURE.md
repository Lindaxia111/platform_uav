# 项目结构与模块职责

当前使用可从项目根目录直接运行的 Python 包布局，不需要安装第三方包或先打包。`workbench/` 即平台源码包；将来确有发布需求时，再统一评估打包与目录迁移。

```text
platform/
├── AGENTS.md                 后续开发约束的入口
├── SESSION_HANDOFF.md        当前进度与会话交接
├── README.md                 用户入口与功能说明
├── main.py                   原命令兼容入口
├── 启动平台.cmd              打开界面
├── 一键验证.cmd              运行默认 A/B 仿真
├── 检查项目.cmd              运行开发检查
├── workbench/                平台源码
│   ├── __main__.py           python -m workbench 入口
│   ├── cli.py                命令解析
│   ├── gui.py                Tkinter 交互界面
│   ├── model.py              工程模型检查与归一化
│   ├── experiment.py         实验编排与证据归档
│   ├── planning.py           算法契约、进程调用与公共航线
│   ├── plugin_worker.py      独立算法子进程入口
│   ├── afsim.py              场景、引擎与回放适配
│   ├── metrics.py            回放轨迹与覆盖评价
│   └── report.py             SVG 轨迹和 HTML 结果预览
├── algorithms/               可替换的独立算法包
├── examples/
│   ├── coverage_project.json 默认工程模型
│   └── results/              经验证的演示证据和相对路径索引
├── tests/                    模型、算法、指标与界面测试
├── scripts/verify.py          自动检查入口
├── docs/                     使用、架构、规范与验证文档
└── artifacts/                本机开发产物（忽略版本管理）
    ├── archive/              历史测试与 Python 缓存
    ├── logs/                 GUI 等本地日志
    ├── test_runs/            测试用例临时证据；成功时清理
    ├── verification/         统一检查日志
    └── runs/                 显式指定的开发仿真结果
```

`artifacts/` 中的子目录按需创建；正常界面运行仍默认写到 `%TEMP%\uav_workbench_runs`。根目录的 `.editorconfig`、`.gitattributes` 和 `.gitignore` 分别约束编辑格式、Git 文本/二进制处理及本地产物。

## 执行链与依赖

```text
GUI / CLI
    ↓
experiment：检查并归一化工程
    ↓
planning → plugin_worker → algorithms/<id>：生成分配与公共航线
    ↓
afsim：生成 scenario.txt → Mission → replay.aer → 实际轨迹
    ↓
metrics：覆盖与需求评价 → report：轨迹预览和差异报告
```

`model.py` 提供通用数据读写与模型契约。界面和 CLI 共用实验编排；算法不直接依赖界面；报告消费评价结果，不重新执行算法或仿真。引擎产生的实际轨迹是覆盖评价输入，计划航线只用于规划与对照。

扩展新模块时，按任务涉及的层修改：模型与校验 → 规划/引擎适配 → 评价 → 展示，并通过相应测试确认数据契约。详细约束见 [开发规范](DEVELOPMENT.md)。
