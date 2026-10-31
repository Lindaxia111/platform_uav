"""Task construction, isolated algorithm calls, and common route generation."""

import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .model import read_json, write_json


class AlgorithmError(ValueError):
    pass


def package_info(package):
    package = Path(package).resolve()
    manifest = read_json(package / "manifest.json")
    if not isinstance(manifest, dict):
        raise AlgorithmError("算法清单必须为对象")
    required = {"api_version": "0.1", "category": "task_allocation", "execution_mode": "offline_plan"}
    for key, value in required.items():
        if manifest.get(key) != value:
            raise AlgorithmError(f"算法包 {key} 必须为 {value}")
    if not isinstance(manifest.get("id"), str) or not manifest["id"] or not isinstance(manifest.get("version"), str):
        raise AlgorithmError("算法包缺少标识或版本")
    if not isinstance(manifest.get("parameters", {}), dict):
        raise AlgorithmError("算法参数必须为对象")
    entry = manifest.get("entrypoint", "")
    if not isinstance(entry, str) or entry.count(":") != 1:
        raise AlgorithmError("算法入口需为 文件.py:函数名")
    filename, function = entry.split(":")
    source = (package / filename).resolve()
    if package not in source.parents or not source.is_file() or source.suffix != ".py" or not function.isidentifier():
        raise AlgorithmError("算法入口文件或函数无效")
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*")):
        if not path.is_file() or any(part in ("__pycache__", ".venv", ".git") for part in path.parts):
            continue
        digest.update(path.relative_to(package).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return {**manifest, "package_path": str(package), "sha256": digest.hexdigest()}


def make_tasks(config):
    task = config["effective"]["coverage_task"]
    padding = config["effective"]["serpentine_router"]["turn_padding_m"]
    count = math.ceil(task["width_m"] / task["lane_spacing_m"])
    return [
        {"id": f"STRIP_{i + 1:03d}", "x_m": (i + 0.5) * task["width_m"] / count,
         "start_y_m": -padding, "end_y_m": task["height_m"] + padding,
         "length_m": task["height_m"] + 2 * padding}
        for i in range(count)
    ]


def make_request(config):
    return {
        "api_version": "0.1", "task_type": "strip_allocation", "coordinate_system": "local_east_north_m",
        "seed": config["effective"]["task_allocator"]["seed"],
        "members": config["effective"]["uav_fleet"]["uavs"],
        "tasks": make_tasks(config), "parameters": {},
        "constraints": {"unique_assignment": True, "ordering": "result_list_per_member",
                        "route_policy": "nearest_endpoint_then_strip", "horizon_s": config["engine"]["horizon_s"]},
    }


def validate_plan(result, request):
    if not isinstance(result, dict) or result.get("status") not in ("ok", "partial", "infeasible"):
        raise AlgorithmError("算法必须返回含 status 的结果对象")
    assignments = result.get("assignments")
    unassigned = result.get("unassigned")
    if not isinstance(assignments, list) or not isinstance(unassigned, list):
        raise AlgorithmError("assignments 和 unassigned 必须为列表")
    tasks = {t["id"] for t in request["tasks"]}
    members = {u["id"] for u in request["members"]}
    seen = set()
    for assignment in assignments:
        if not isinstance(assignment, dict):
            raise AlgorithmError("分配记录必须为对象")
        task_id, member_id = assignment.get("task_id"), assignment.get("uav_id")
        if not isinstance(task_id, str) or task_id not in tasks or task_id in seen or not isinstance(member_id, str) or member_id not in members:
            raise AlgorithmError("分配包含重复任务、未知任务或未知无人机")
        seen.add(task_id)
    for item in unassigned:
        if not isinstance(item, dict) or not isinstance(item.get("task_id"), str) or item["task_id"] not in tasks or item["task_id"] in seen or not isinstance(item.get("reason"), str) or not item["reason"].strip():
            raise AlgorithmError("未分配任务需要唯一合法编号及原因")
        seen.add(item["task_id"])
    if seen != tasks:
        raise AlgorithmError("任务未全部说明归属；不允许静默遗漏")
    if (result["status"] == "ok" and unassigned) or (result["status"] == "partial" and (not assignments or not unassigned)) or (result["status"] == "infeasible" and assignments):
        raise AlgorithmError("结果状态与分配内容不一致")
    return result


def call_algorithm(package, request, run_dir, budget_s, project_root):
    info = package_info(package)
    snapshot = run_dir / "algorithm_package"
    shutil.copytree(package, snapshot, ignore=shutil.ignore_patterns("__pycache__", ".venv", ".git"))
    if package_info(snapshot)["sha256"] != info["sha256"]:
        raise AlgorithmError("算法包复制期间发生变化，请重试")
    request = {**request, "parameters": info.get("parameters", {})}
    write_json(run_dir / "algorithm.json", info)
    write_json(run_dir / "algorithm_request.json", request)
    started = time.perf_counter()
    command = [sys.executable, "-m", "workbench.plugin_worker", str(snapshot.resolve()),
               str(run_dir / "algorithm_request.json"), str(run_dir / "algorithm_result.json")]
    try:
        process = subprocess.run(command, cwd=project_root, capture_output=True, timeout=budget_s, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        (run_dir / "algorithm.log").write_bytes((exc.stdout or b"") + (exc.stderr or b""))
        raise AlgorithmError(f"算法超过规划预算 {budget_s} 秒（含子进程启动）") from exc
    elapsed = time.perf_counter() - started
    (run_dir / "algorithm.log").write_bytes(process.stdout + process.stderr)
    if process.returncode:
        raise AlgorithmError(f"算法进程失败，退出码 {process.returncode}，详见 algorithm.log")
    try:
        result = validate_plan(read_json(run_dir / "algorithm_result.json"), request)
    except (OSError, json.JSONDecodeError) as exc:
        raise AlgorithmError("算法未产生合法结果文件") from exc
    return info, result, elapsed


def make_routes(request, result):
    tasks = {t["id"]: t for t in request["tasks"]}
    routes = {u["id"]: [list(u["start_xy_m"])] for u in request["members"]}
    for assignment in result["assignments"]:
        task = tasks[assignment["task_id"]]
        route = routes[assignment["uav_id"]]
        ends = [[task["x_m"], task["start_y_m"]], [task["x_m"], task["end_y_m"]]]
        if math.dist(route[-1], ends[1]) < math.dist(route[-1], ends[0]):
            ends.reverse()
        for point in ends:
            if math.dist(route[-1], point) > 1e-6:
                route.append(point)
    return routes
