"""Metrics calculated from recorded motion, never from user-claimed scores."""

import math


def segment_distance_sq(x, y, a, b):
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    denominator = dx * dx + dy * dy
    weight = 0.0 if denominator == 0 else max(0.0, min(1.0, ((x - a["x"]) * dx + (y - a["y"]) * dy) / denominator))
    return (x - a["x"] - weight * dx) ** 2 + (y - a["y"] - weight * dy) ** 2


def evaluate(config, trajectories):
    task = config["effective"]["coverage_task"]
    monitor = config["effective"]["coverage_monitor"]
    resolution = monitor["grid_resolution_m"]
    nx, ny = math.ceil(task["width_m"] / resolution), math.ceil(task["height_m"] / resolution)
    dx, dy = task["width_m"] / nx, task["height_m"] / ny
    cells = [(i * dx + dx / 2, j * dy + dy / 2) for j in range(ny) for i in range(nx)]
    covered = set()
    members_cover = {name: set() for name in trajectories}
    events = []
    total_distance = 0.0
    radius_sq = monitor["footprint_radius_m"] ** 2
    for name, points in trajectories.items():
        events.append((points[0]["t"], name, points[0], points[0]))
        for a, b in zip(points, points[1:]):
            events.append((b["t"], name, a, b))
            total_distance += math.hypot(b["x"] - a["x"], b["y"] - a["y"])
    target = next(r["threshold"] for r in config["requirements"] if r["metric"] == "coverage_pct")
    threshold_time = None
    curve = []
    last_t = None
    for t, name, a, b in sorted(events, key=lambda event: event[0]):
        for i, (x, y) in enumerate(cells):
            if i not in members_cover[name] and segment_distance_sq(x, y, a, b) <= radius_sq:
                members_cover[name].add(i)
                covered.add(i)
        percentage = 100 * len(covered) / len(cells)
        if threshold_time is None and percentage + 1e-9 >= target:
            threshold_time = t
        if last_t == t:
            curve[-1]["coverage_pct"] = percentage
        else:
            curve.append({"t": t, "coverage_pct": percentage})
            last_t = t
    metrics = {
        "coverage_pct": 100 * len(covered) / len(cells),
        "coverage_threshold_time_s": threshold_time,
        "total_distance_m": total_distance,
        "overlap_between_members_pct": 100 * sum(sum(i in s for s in members_cover.values()) > 1 for i in range(len(cells))) / len(cells),
    }
    statuses = []
    for req in config["requirements"]:
        value = metrics.get(req["metric"])
        passed = value is not None and (value >= req["threshold"] if req["operator"] == ">=" else value <= req["threshold"])
        statuses.append({**req, "actual": value, "status": "pass" if passed else "fail",
                         "reason": "已达到判据" if passed else "未达到覆盖阈值，时间值不适用" if value is None else "未满足需求阈值",
                         "trace": [t for t in config["traceability"] if t["requirement"] == req["id"]],
                         "evidence": ["trajectories.json", "coverage_curve.json", "metrics.json", "replay.aer"]})
    return {"metrics": metrics, "requirements": statuses, "coverage_curve": curve,
            "grid": {"nx": nx, "ny": ny, "cell_width_m": dx, "cell_height_m": dy, "covered_indices": sorted(covered)},
            "method": {"version": "coverage_grid_capsule_v1", "sampling_interval_s": monitor["sample_interval_s"],
                       "coverage_target_pct": target, "time_resolution_note": "覆盖时刻取轨迹段终点采样时刻，段内按直线扫掠估算，弯道仍有离散化误差",
                       "assumptions": "小区域局部平面；全程启用的理想圆形足迹；网格中心代表等面积单元；不代表真实发现率"}}


METRIC_META = {
    "coverage_pct": ("有效覆盖率", "百分点", "higher"),
    "coverage_threshold_time_s": ("达到覆盖阈值的时间", "s", "lower"),
    "total_distance_m": ("总航程", "m", "lower"),
    "overlap_between_members_pct": ("成员间重叠覆盖率", "百分点", "lower"),
}


def compare_metrics(baseline, candidate):
    rows = []
    for key, (label, unit, direction) in METRIC_META.items():
        a, b = baseline.get(key), candidate.get(key)
        delta = None if a is None or b is None else b - a
        rows.append({"metric": key, "label": label, "unit": unit, "direction": direction,
                     "baseline": a, "candidate": b, "delta": delta,
                     "relative_change_pct": None if delta is None or abs(a) < 1e-9 else 100 * delta / abs(a),
                     "note": "未达覆盖阈值的时间不参与差值计算" if delta is None else "原始差异 = 候选 - 参照；优劣结合指标方向及任务需求判断"})
    return rows
