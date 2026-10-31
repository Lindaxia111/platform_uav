"""Preliminary local experiment document, independent of future report formats."""

import html


def escape(value):
    return html.escape(str(value), quote=True)


def format_value(value):
    return "不适用" if value is None else f"{value:.3f}"


def map_svg(config, evaluation, trajectories, routes):
    task = config["effective"]["coverage_task"]
    pad = config["effective"]["serpentine_router"]["turn_padding_m"] + 50
    width, height = task["width_m"], task["height_m"]
    sx = lambda x: x + pad
    sy = lambda y: height + pad - y
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="覆盖网格与实际轨迹" viewBox="0 0 {width+2*pad} {height+2*pad}" style="width:100%;max-height:430px;background:#f5f8fc">',
             f'<rect x="{pad}" y="{pad}" width="{width}" height="{height}" fill="#e0e7ee" stroke="#92a0b0"/>']
    grid = evaluation["grid"]
    dx, dy = grid["cell_width_m"], grid["cell_height_m"]
    for index in grid["covered_indices"]:
        row, col = divmod(index, grid["nx"])
        parts.append(f'<rect x="{sx(col*dx)}" y="{sy((row+1)*dy)}" width="{dx}" height="{dy}" fill="#b6e5cc"/>')
    colors = ["#1269c7", "#d26b21", "#8951af", "#138b89", "#b83b61"]
    for i, (name, points) in enumerate(trajectories.items()):
        color = colors[i % len(colors)]
        planned = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in routes[name])
        actual = " ".join(f"{sx(p['x']):.2f},{sy(p['y']):.2f}" for p in points)
        parts.append(f'<polyline points="{planned}" stroke="{color}" fill="none" stroke-width="1.5" stroke-dasharray="7,5" opacity="0.5"/>')
        parts.append(f'<polyline points="{actual}" stroke="{color}" fill="none" stroke-width="3"/>')
        first = points[0]
        parts.append(f'<circle cx="{sx(first["x"])}" cy="{sy(first["y"])}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{sx(first["x"])+8}" y="{sy(first["y"])-8}" font-size="14" fill="{color}">{escape(name)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def write_report(directory, comparison, config, evaluations):
    rows = "".join(f'<tr><td>{escape(row["label"])}</td><td>{format_value(row["baseline"])}</td><td>{format_value(row["candidate"])}</td><td>{format_value(row["delta"])} {escape(row["unit"])}</td><td>{format_value(row["relative_change_pct"])}%</td></tr>' for row in comparison.get("differences", []))
    panels = []
    for run in comparison["runs"]:
        run_id = run["run_id"]
        name = run.get("algorithm", {}).get("name", run.get("package", "算法"))
        if run["status"] != "completed":
            panels.append(f'<section><h2>{escape(name)}</h2><p class="bad">{escape(run["status"])}：{escape(run.get("error", ""))}</p><a href="{run_id}/run.json">执行记录</a></section>')
            continue
        evidence = evaluations[run_id]
        table = "".join(f'<tr><td>{escape(r["id"])} · {escape(r["name"])}</td><td>{format_value(r["actual"])}</td><td>{escape(r["operator"])} {r["threshold"]} {escape(r["unit"])}</td><td class="{"good" if r["status"]=="pass" else "bad"}">{"通过" if r["status"]=="pass" else "未通过"}</td></tr>' for r in evidence["requirements"])
        panels.append(f'<section><h2>{escape(name)}</h2><p>版本 {escape(run["algorithm"]["version"])} · 算法包 {escape(run["algorithm"]["sha256"][:12])} · 本机规划进程耗时 {run["planning_wall_s"]:.3f} 秒</p>{evidence["map_svg"]}<p class="muted">绿色：覆盖网格；实线：AFSIM 回放轨迹；虚线：计划航线。局部坐标单位为米。</p><table><tr><th>需求</th><th>实际值</th><th>判据</th><th>结果</th></tr>{table}</table><p><a href="{run_id}/scenario.txt">生成场景</a> · <a href="{run_id}/source_map.json">模型来源映射</a> · <a href="{run_id}/metrics.json">指标与追踪证据</a> · <a href="{run_id}/engine.log">引擎日志</a> · <a href="{run_id}/replay.aer">回放数据</a></p></section>')
    checks = "".join(f'<li>{escape(i["path"])}：{escape(i["message"])}</li>' for i in comparison["model_checks"])
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>实验结果预览 · {escape(config['name'])}</title>
<style>body{{font:15px/1.7 "Microsoft YaHei",sans-serif;background:#edf2f7;color:#20304a;max-width:1120px;margin:32px auto;padding:0 22px}}h1{{font-size:28px}}h2{{font-size:20px}}section{{background:white;padding:24px;margin:20px 0;border:1px solid #dce4ee;border-radius:12px}}table{{width:100%;border-collapse:collapse;margin:14px 0}}th,td{{text-align:left;padding:11px;border-bottom:1px solid #e4e9ef}}th{{background:#f4f7fb}}a{{color:#1269c7}}.muted{{color:#62718a}}.good{{color:#087647}}.bad{{color:#ba382e}}code{{background:#edf2f7;padding:2px 5px}}.tag{{display:inline-block;padding:4px 12px;background:#e0eaff;color:#284fa4;border-radius:20px}}</style>
<header><span class="tag">UAV Workbench · 本机 AFSIM 实测</span><h1>{escape(config['name'])}</h1><p>实验结果预览 · {escape(comparison['comparison_id'])}</p></header>
<section><h2>比较范围</h2><p>一次确定性任务实例，使用相同工程模型、公共航线生成器、运动模型和评价口径，只替换离线任务分配算法。未进行统计显著性或非劣性推断。</p><p>原始差异统一为候选 B − 参照 A。覆盖率差异使用百分点；相对变化率单列。未达到覆盖阈值时，时间不适用，不使用仿真上限代替。</p><table><tr><th>指标</th><th>参照 A</th><th>候选 B</th><th>原始差异</th><th>相对变化</th></tr>{rows}</table><p>比较状态：{escape(comparison['status'])}。失败运行保留记录，不静默排除。</p></section>
{''.join(panels)}<section><h2>模型检查与适用范围</h2><ul>{checks}</ul><p>覆盖率采用等面积网格中心和相邻回放点间的直线扫掠估算；时间分辨率为采样间隔，弯道有离散化误差。规划耗时是本机进程耗时，不能直接解释为机载实时性能。</p><p>本预览用于验证数据闭环，正式报告版式后续确定。未实现自由拖拽行为编译、通信与共享资源仿真、在线 Python 控制、定向测试选择和真实探测模型。</p><p><a href="comparison.json">完整差异数据</a> · <a href="engineering_model.json">工程模型与有效参数</a></p></section></html>'''
    target = directory / "preview.html"
    target.write_text(document, encoding="utf-8")
    return target
