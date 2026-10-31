"""Typed module model, semantic checks, and normalized configuration."""

import copy
import json
import math
import re
from pathlib import Path


REGISTRY = {
    "coverage_task": {"outputs": {"tasks": "tasks", "region": "region"}, "inputs": {}},
    "uav_fleet": {"outputs": {"members": "members", "trajectory": "trajectory"}, "inputs": {"routes": "routes"}},
    "task_allocator": {"outputs": {"assignment": "assignment"}, "inputs": {"tasks": "tasks", "members": "members"}},
    "serpentine_router": {"outputs": {"routes": "routes"}, "inputs": {"assignment": "assignment"}},
    "coverage_monitor": {"outputs": {}, "inputs": {"trajectory": "trajectory", "region": "region"}},
}
STEPS = ["initialize", "allocate", "build_routes", "simulate", "evaluate"]
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def parameters(model, kind):
    return next(m["parameters"] for m in model["modules"] if m["type"] == kind)


def check_model(model, project_root, check_engine=True):
    issues = []

    def add(level, path, message):
        issues.append({"level": level, "path": path, "message": message})

    def number(value, path, low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            add("error", path, f"数值必须在 {low} 到 {high} 之间，且不能为空或非有限值")
            return False
        return True

    if not isinstance(model, dict):
        return [{"level": "error", "path": "project", "message": "工程必须为对象"}]
    if model.get("schema_version") != "0.1":
        add("error", "schema_version", "当前只支持工程模型 0.1")
    if not isinstance(model.get("name"), str) or not model["name"].strip():
        add("error", "name", "工程需要非空名称")
    if not IDENTIFIER.fullmatch(str(model.get("id", ""))):
        add("error", "id", "工程编号需要以英文字母开头，只含字母、数字和下划线")
    modules = model.get("modules", [])
    if not isinstance(modules, list) or any(not isinstance(m, dict) for m in modules):
        add("error", "modules", "模块必须为对象列表")
        return issues
    by_id = {}
    by_type = {}
    for i, module in enumerate(modules):
        mid, kind = module.get("id"), module.get("type")
        if not isinstance(mid, str) or not IDENTIFIER.fullmatch(mid) or mid in by_id:
            add("error", f"modules[{i}].id", "模块编号无效或重复")
            continue
        by_id[mid] = module
        if not isinstance(kind, str) or kind not in REGISTRY:
            add("error", mid, f"未支持的模块类型：{kind}")
        elif kind in by_type:
            add("error", mid, f"首期每种模块只能有一个：{kind}")
        else:
            by_type[kind] = module
        if not isinstance(module.get("parameters"), dict):
            add("error", mid, "缺少参数对象")
    for kind in REGISTRY:
        if kind not in by_type:
            add("error", "modules", f"缺少必需模块：{kind}")

    connections = model.get("connections", [])
    connected = set()
    if not isinstance(connections, list):
        add("error", "connections", "连接必须为列表")
        connections = []
    for i, connection in enumerate(connections):
        if not isinstance(connection, dict):
            add("error", f"connections[{i}]", "连接必须为对象")
            continue
        resolved = []
        for direction, field in (("outputs", "from"), ("inputs", "to")):
            endpoint = connection.get(field, "")
            if not isinstance(endpoint, str) or endpoint.count(".") != 1:
                add("error", f"connections[{i}].{field}", "端口需使用 模块编号.端口名")
                break
            mid, port = endpoint.split(".")
            kind = by_id.get(mid, {}).get("type")
            if not isinstance(kind, str):
                kind = None
            port_type = REGISTRY.get(kind, {}).get(direction, {}).get(port)
            if not port_type:
                add("error", endpoint, "模块、端口或连接方向无效")
                break
            resolved.append(port_type)
        if len(resolved) == 2:
            target = connection["to"]
            if resolved[0] != resolved[1]:
                add("error", target, "连接两端的数据类型不一致")
            elif target in connected:
                add("error", target, "一个必需输入只能有一个提供方")
            else:
                connected.add(target)
    for mid, module in by_id.items():
        kind = module.get("type")
        for port in REGISTRY.get(kind if isinstance(kind, str) else None, {}).get("inputs", {}):
            if f"{mid}.{port}" not in connected:
                add("error", f"{mid}.{port}", "必需输入未连接")
    behavior = model.get("behavior", {})
    if not isinstance(behavior, dict) or behavior.get("template") != "offline_coverage_v1" or behavior.get("steps") != STEPS:
        add("error", "behavior", "首期只支持已定义的离线覆盖执行流程")

    if any(i["level"] == "error" for i in issues):
        return issues
    task = parameters(model, "coverage_task")
    fleet = parameters(model, "uav_fleet")
    alloc = parameters(model, "task_allocator")
    monitor = parameters(model, "coverage_monitor")
    router = parameters(model, "serpentine_router")
    for key, lo, hi in (("width_m", 20, 5000), ("height_m", 20, 5000), ("lane_spacing_m", 5, 1000), ("origin_lat_deg", -75, 75), ("origin_lon_deg", -170, 170)):
        number(task.get(key), f"TASK.{key}", lo, hi)
    for key, lo, hi in (("footprint_radius_m", 1, 2000), ("grid_resolution_m", 1, 500), ("sample_interval_s", 0.1, 5)):
        number(monitor.get(key), f"MONITOR.{key}", lo, hi)
    number(router.get("turn_padding_m"), "ROUTE.turn_padding_m", 0, 1000)
    number(fleet.get("altitude_m"), "FLEET.altitude_m", 20, 5000)
    number(fleet.get("bank_angle_limit_deg"), "FLEET.bank_angle_limit_deg", 10, 75)
    uavs = fleet.get("uavs", [])
    if not isinstance(uavs, list) or not 1 <= len(uavs) <= 10 or any(not isinstance(u, dict) for u in uavs):
        add("error", "FLEET.uavs", "首期支持 1—10 架无人机对象")
        uavs = []
    ids = set()
    for i, uav in enumerate(uavs):
        uid = uav.get("id")
        if not isinstance(uid, str) or not IDENTIFIER.fullmatch(uid) or uid in ids:
            add("error", f"FLEET.uavs[{i}].id", "无人机编号无效或重复")
        ids.add(str(uid))
        number(uav.get("speed_mps"), f"{uid}.speed_mps", 3, 50)
        xy = uav.get("start_xy_m")
        if not isinstance(xy, list) or len(xy) != 2:
            add("error", f"{uid}.start_xy_m", "初始位置需要东、北两个坐标，单位米")
        else:
            for j, value in enumerate(xy):
                number(value, f"{uid}.start_xy_m[{j}]", -10000, 10000)
    packages = alloc.get("algorithm_packages")
    if not isinstance(packages, list) or len(packages) != 2 or any(not isinstance(p, str) for p in packages):
        add("error", "ALLOC.algorithm_packages", "首期需要指定两个算法包路径")
    else:
        for package in packages:
            if not (Path(project_root) / package / "manifest.json").is_file():
                add("error", "ALLOC.algorithm_packages", f"算法包缺少 manifest.json：{package}")
    number(alloc.get("planning_budget_s"), "ALLOC.planning_budget_s", 0.1, 120)
    seed = alloc.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**31:
        add("error", "ALLOC.seed", "种子需为非负 31 位整数")
    engine = model.get("engine", {})
    if not isinstance(engine, dict):
        add("error", "engine", "缺少引擎配置")
        engine = {}
    number(engine.get("horizon_s"), "engine.horizon_s", 5, 3600)
    number(engine.get("wall_timeout_s"), "engine.wall_timeout_s", 1, 600)
    home = engine.get("afsim_home", "")
    if check_engine and (not isinstance(home, str) or not (Path(home) / "bin" / "mission.exe").is_file() or not (Path(home) / "bin" / "python" / "pymystic.py").is_file()):
        add("error", "engine.afsim_home", "未找到 Mission 或随附的 Python 回放读取模块")

    reqs = model.get("requirements", [])
    if not isinstance(reqs, list) or not reqs or any(not isinstance(r, dict) for r in reqs):
        add("error", "requirements", "需要至少一项需求对象")
        reqs = []
    req_ids = set()
    for req in reqs:
        rid = req.get("id")
        if not isinstance(rid, str) or not IDENTIFIER.fullmatch(rid) or rid in req_ids:
            add("error", "requirements.id", "需求编号无效或重复")
        req_ids.add(str(rid))
        metric = req.get("metric")
        if metric not in ("coverage_pct", "coverage_threshold_time_s"):
            add("error", str(rid), "首期只支持覆盖率和达到阈值时间需求")
        expected = (">=", "%") if metric == "coverage_pct" else ("<=", "s")
        if (req.get("operator"), req.get("unit")) != expected:
            add("error", str(rid), "需求运算符或单位与指标不匹配")
        number(req.get("threshold"), str(rid), 0.01, 100 if metric == "coverage_pct" else 3600)
    if len([r for r in reqs if r.get("metric") == "coverage_pct"]) != 1:
        add("error", "requirements", "需且仅需一项覆盖率需求，用作时间指标的目标阈值")

    caps = model.get("capabilities", [])
    funcs = model.get("functions", [])
    traces = model.get("traceability", [])
    for name, values in (("capabilities", caps), ("functions", funcs), ("traceability", traces)):
        if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
            add("error", name, "必须为对象列表")
    if not any(i["level"] == "error" for i in issues):
        valid_ids = all(isinstance(v.get("id"), str) and IDENTIFIER.fullmatch(v["id"]) for v in caps + funcs)
        if not valid_ids:
            add("error", "traceability", "能力与功能需要有效编号")
            return issues
        cap_ids = {c["id"] for c in caps}
        fun_ids = {f["id"] for f in funcs}
        if not cap_ids or not fun_ids or len(cap_ids) != len(caps) or len(fun_ids) != len(funcs):
            add("error", "traceability", "能力或功能编号缺失、重复")
        for f in funcs:
            if not isinstance(f.get("module"), str) or f["module"] not in by_id:
                add("error", str(f.get("id")), "功能缺少有效主责任模块")
        for trace in traces:
            if not isinstance(trace.get("requirement"), str) or trace["requirement"] not in req_ids:
                add("error", "traceability", "追踪引用了不存在的需求")
        for rid in req_ids:
            matching = [t for t in traces if t.get("requirement") == rid]
            if not matching:
                add("error", rid, "需求缺少能力、功能与验证用例追踪")
            for trace in matching:
                valid_functions = isinstance(trace.get("functions"), list) and all(isinstance(v, str) and v in fun_ids for v in trace["functions"])
                if not isinstance(trace.get("capability"), str) or trace["capability"] not in cap_ids or not isinstance(trace.get("test_case"), str) or not trace["test_case"] or not trace.get("functions") or not valid_functions:
                    add("error", rid, "需求追踪引用不存在或缺少验证用例")
    if not any(i["level"] == "error" for i in issues):
        nx = math.ceil(task["width_m"] / monitor["grid_resolution_m"])
        ny = math.ceil(task["height_m"] / monitor["grid_resolution_m"])
        lanes = math.ceil(task["width_m"] / task["lane_spacing_m"])
        if nx * ny > 10000 or lanes > 100:
            add("error", "TASK", "首期最多 100 条条带、10000 个评价网格，请降低分辨率或区域大小")
        estimated_work = math.ceil(engine["horizon_s"] / monitor["sample_interval_s"]) * len(uavs) * nx * ny
        if estimated_work > 10000000:
            add("error", "MONITOR", "评价规模超出原型范围，请增大网格或采样间隔、缩短仿真时限")
        if task["width_m"] / lanes > 2 * monitor["footprint_radius_m"]:
            add("warning", "MONITOR.footprint_radius_m", "足迹宽度小于条带间距，完整执行仍可能存在覆盖缺口")
        add("warning", "model_fidelity", "采用简化空中运动、平坦矩形区域及全程启用的理想圆形覆盖足迹；未建模探测概率、通信、碰撞、真实能耗与在线重规划")
    return issues


def normalize(model):
    config = copy.deepcopy(model)
    config["effective"] = {kind: copy.deepcopy(parameters(model, kind)) for kind in REGISTRY}
    return config
