# 启动平台与查看 AFSIM 结果

本机 AFSIM 根目录：`D:\afsim\afsim-2.9.0-win64`。若换机器，在界面的“检查与执行”中选择实际安装目录；工程模型也保存此项配置。

## 启动与执行

双击根目录 `启动平台.cmd`，或在根目录运行：

```powershell
python -m workbench gui
```

打开“检查与执行”，确认 AFSIM 目录，点击“检查工程模型”，再点击“生成场景并运行 A/B 比较”。完成后在“比较结果”点击“打开轨迹与结果预览”或“打开证据目录”。平台通过 Mission 执行仿真，查看动画需要另开 Mystic。

默认运行结果放在 `%TEMP%\uav_workbench_runs` 下的独立目录，可将该路径粘贴到资源管理器地址栏。`run_00` 对应参照算法，`run_01` 对应候选算法。

## 用 Mystic 看回放

启动 `D:\afsim\afsim-2.9.0-win64\bin\mystic.exe`，通过 `File → Open` 打开所需运行目录里的 `replay.aer`，然后使用时间控制器播放。

以下命令直接打开项目附带的参照 A 演示：

```powershell
& "D:\afsim\afsim-2.9.0-win64\bin\mystic.exe" "D:\platform\examples\results\20261027_183740_6a6cec2a\run_00\replay.aer"
```

候选 B 使用同一实验下的 `run_01\replay.aer`。查看新运行时，换成其实际结果目录。

## 用 Wizard 看场景

Wizard 加载 `scenario.txt`，可查看生成的平台、航线和场景定义：

```powershell
& "D:\afsim\afsim-2.9.0-win64\bin\wizard.exe" "D:\platform\examples\results\20261027_183740_6a6cec2a\run_00\scenario.txt"
```

若需修改验证条件，在平台的工程模型中修改，再生成一个新实验。查看或编辑旧证据时，先复制到开发目录，保持已验证演示快照可追溯。

## 文件用途

| 文件 | 用途 |
|---|---|
| `scenario.txt` | Mission/Wizard 场景输入 |
| `replay.aer` | Mystic 回放输入 |
| `engine.log` | 引擎运行日志，运行失败时优先检查 |
| `source_map.json` | 工程模型到场景文本的来源映射 |
| `trajectories.json` | 从真实回放提取的轨迹 |
| `metrics.json` | 本次指标、判据及需求结果 |
| `preview.html` | 实验根目录中的网页预览，可比较 A/B |

已有演示的网页入口：[打开演示预览](../examples/results/20261027_183740_6a6cec2a/preview.html)。开发检查与真实引擎验证命令见 [开发规范](DEVELOPMENT.md)。
