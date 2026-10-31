"""Model-to-evidence orchestration with durable failure records."""

import hashlib
import json
import os
import platform
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .afsim import generate_scenario, read_trajectories, run_mission
from .metrics import compare_metrics, evaluate
from .model import check_model, normalize, read_json, write_json
from .planning import call_algorithm, make_request, make_routes
from .report import map_svg, write_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def default_output_root():
    temp_root = os.environ.get("TEMP")
    return Path(temp_root) / "uav_workbench_runs" if temp_root else PROJECT_ROOT / "artifacts" / "runs"


def run_comparison(model, output_root=None, progress=None):
    progress = progress or (lambda text: None)
    checks = check_model(model, PROJECT_ROOT)
    errors = [i for i in checks if i["level"] == "error"]
    if errors:
        raise ValueError("模型检查未通过：\n" + "\n".join(f"{i['path']}：{i['message']}" for i in errors))
    config = normalize(model)
    comparison_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    directory = (Path(output_root) if output_root else default_output_root()).resolve() / comparison_id
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "engineering_model.json", config)
    request = make_request(config)
    write_json(directory / "common_task_instance.json", request)
    comparison = {
        "schema_version": "0.1", "comparison_id": comparison_id, "status": "running", "model_checks": checks,
        "model_sha256": hashlib.sha256(json.dumps(model, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
        "common_instance_sha256": hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest(),
        "runtime": {"python": sys.version, "platform": platform.platform(), "workbench_version": "0.1.0"},
        "experiment_scope": "single_deterministic_instance_offline_allocation", "runs": [], "differences": [],
    }
    write_json(directory / "comparison.json", comparison)
    evaluations = {}
    allocator = config["effective"]["task_allocator"]
    for index, package_path in enumerate(allocator["algorithm_packages"]):
        run_id = f"run_{index:02d}"
        run_dir = directory / run_id
        run_dir.mkdir()
        run = {"run_id": run_id, "package": package_path, "status": "running", "stage": "algorithm"}
        comparison["runs"].append(run)
        write_json(run_dir / "run.json", run)
        progress(f"{index + 1}/2：检查并运行算法 {package_path}")
        try:
            info, plan, elapsed = call_algorithm(PROJECT_ROOT / package_path, request, run_dir,
                                                 allocator["planning_budget_s"], PROJECT_ROOT)
            run.update({"algorithm": info, "planning_wall_s": elapsed, "unassigned_count": len(plan["unassigned"])})
            if plan["status"] == "infeasible":
                run.update({"status": "infeasible", "error": "算法返回任务不可行；未生成仿真指标"})
            else:
                routes = make_routes(request, plan)
                run["stage"] = "generation"
                progress(f"{index + 1}/2：从工程模型生成 AFSIM 场景")
                generate_scenario(config, routes, run_dir)
                run["stage"] = "simulation"
                progress(f"{index + 1}/2：运行本机 AFSIM")
                run["engine"] = run_mission(config, run_dir)
                run["stage"] = "evaluation"
                trajectories = read_trajectories(config, run_dir)
                evaluation = evaluate(config, trajectories)
                write_json(run_dir / "metrics.json", {k: v for k, v in evaluation.items() if k not in ("coverage_curve", "grid")})
                write_json(run_dir / "coverage_curve.json", evaluation["coverage_curve"])
                write_json(run_dir / "coverage_grid.json", evaluation["grid"])
                evaluation["map_svg"] = map_svg(config, evaluation, trajectories, routes)
                (run_dir / "map.svg").write_text(evaluation["map_svg"], encoding="utf-8")
                evaluations[run_id] = evaluation
                run.update({"status": "completed", "stage": "complete", "metrics": evaluation["metrics"],
                            "requirements": evaluation["requirements"], "all_requirements_pass": all(r["status"] == "pass" for r in evaluation["requirements"])})
        except Exception as exc:
            run.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        write_json(run_dir / "run.json", run)
        write_json(directory / "comparison.json", comparison)
    if all(r["status"] == "completed" for r in comparison["runs"]):
        comparison["status"] = "completed"
        comparison["differences"] = compare_metrics(comparison["runs"][0]["metrics"], comparison["runs"][1]["metrics"])
    else:
        comparison["status"] = "incomplete"
    write_json(directory / "comparison.json", comparison)
    preview = write_report(directory, comparison, config, evaluations)
    progress(f"比较完成：{preview}")
    return {"directory": str(directory), "preview": str(preview), "comparison": comparison}
