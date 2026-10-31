import copy
import math
import shutil
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from workbench.afsim import EARTH_A, EARTH_E2, ecef_to_xy, xy_to_geo
from workbench.experiment import PROJECT_ROOT, run_comparison
from workbench.metrics import compare_metrics, evaluate, segment_distance_sq
from workbench.model import check_model, normalize, parameters, read_json, write_json
from workbench.planning import AlgorithmError, call_algorithm, make_request, make_routes, validate_plan


@contextmanager
def test_directory():
    # Normal mkdir avoids restrictive temp ACLs in some Windows runtimes.
    # Keep failed-test evidence; remove successful cases to prevent buildup.
    directory = PROJECT_ROOT / "artifacts" / "test_runs" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    yield str(directory)
    shutil.rmtree(directory)


class ModelChecks(unittest.TestCase):
    def setUp(self):
        self.model = read_json(PROJECT_ROOT / "examples/coverage_project.json")

    def errors(self):
        return [i for i in check_model(self.model, PROJECT_ROOT, check_engine=False) if i["level"] == "error"]

    def test_valid_project(self):
        self.assertFalse(self.errors())

    def test_missing_input_is_rejected(self):
        self.model["connections"].pop(0)
        self.assertTrue(any(i["path"] == "ALLOC.tasks" for i in self.errors()))

    def test_wrong_port_type_is_rejected(self):
        self.model["connections"][0]["to"] = "ALLOC.members"
        self.assertTrue(any("类型" in i["message"] for i in self.errors()))

    def test_missing_trace_is_rejected(self):
        self.model["traceability"].pop()
        self.assertTrue(any(i["path"] == "R_TIME" for i in self.errors()))

    def test_unit_mismatch_is_rejected(self):
        self.model["requirements"][0]["unit"] = "m"
        self.assertTrue(self.errors())

    def test_non_finite_and_bool_parameters_are_rejected(self):
        for value in (float("nan"), float("inf"), True, "600", None):
            with self.subTest(value=value):
                parameters(self.model, "coverage_task")["width_m"] = value
                self.assertTrue(self.errors())

    def test_unsupported_behavior_is_rejected(self):
        self.model["behavior"]["steps"].append("online_replan")
        self.assertTrue(self.errors())

    def test_invalid_structures_return_issues(self):
        for key, value in (("modules", None), ("connections", [None]), ("functions", [None]), ("capabilities", [{"id": []}]), ("traceability", [{"requirement": "R_COVER", "functions": 4}])):
            with self.subTest(key=key):
                model = copy.deepcopy(self.model)
                model[key] = value
                self.assertTrue(any(i["level"] == "error" for i in check_model(model, PROJECT_ROOT, check_engine=False)))


class AlgorithmContract(unittest.TestCase):
    def setUp(self):
        self.model = read_json(PROJECT_ROOT / "examples/coverage_project.json")
        self.request = make_request(normalize(self.model))
        self.plan = {"status": "ok", "assignments": [{"task_id": t["id"], "uav_id": "UAV_1"} for t in self.request["tasks"]], "unassigned": []}

    def test_duplicate_or_unknown_assignment_is_rejected(self):
        for update in ({"task_id": "STRIP_002"}, {"uav_id": "MISSING"}):
            with self.subTest(update=update):
                plan = copy.deepcopy(self.plan)
                plan["assignments"][0].update(update)
                with self.assertRaises(AlgorithmError):
                    validate_plan(plan, self.request)

    def test_missing_task_requires_explicit_reason(self):
        plan = copy.deepcopy(self.plan)
        first = plan["assignments"].pop()
        with self.assertRaises(AlgorithmError):
            validate_plan(plan, self.request)
        plan["status"] = "partial"
        plan["unassigned"] = [{"task_id": first["task_id"], "reason": "无可用资源"}]
        self.assertEqual(validate_plan(plan, self.request)["status"], "partial")

    def test_common_router_keeps_idle_member(self):
        routes = make_routes(self.request, self.plan)
        self.assertEqual(routes["UAV_2"], [[550, -60]])
        self.assertEqual(len(routes["UAV_1"]), 12)

    def test_real_plugin_process_and_snapshot(self):
        with test_directory() as temp:
            run = Path(temp)
            info, result, elapsed = call_algorithm(PROJECT_ROOT / "algorithms/round_robin", self.request, run, 5, PROJECT_ROOT)
            self.assertEqual(len(result["assignments"]), len(self.request["tasks"]))
            self.assertTrue((run / "algorithm_package/algorithm.py").is_file())
            self.assertGreater(elapsed, 0)
            self.assertEqual(len(info["sha256"]), 64)

    def test_timeout_keeps_diagnostic_file(self):
        with test_directory() as temp:
            package = Path(temp) / "package"
            run = Path(temp) / "run"
            package.mkdir()
            run.mkdir()
            write_json(package / "manifest.json", {"id": "timeout", "version": "1", "api_version": "0.1", "category": "task_allocation", "execution_mode": "offline_plan", "entrypoint": "algorithm.py:plan"})
            (package / "algorithm.py").write_text("import time\ndef plan(request):\n    time.sleep(3)\n", encoding="utf-8")
            with self.assertRaisesRegex(AlgorithmError, "预算"):
                call_algorithm(package, self.request, run, 0.1, PROJECT_ROOT)
            self.assertTrue((run / "algorithm.log").exists())


class MetricsAndGeometry(unittest.TestCase):
    def model(self):
        model = read_json(PROJECT_ROOT / "examples/coverage_project.json")
        task = parameters(model, "coverage_task")
        task.update({"width_m": 20, "height_m": 20})
        parameters(model, "coverage_monitor").update({"footprint_radius_m": 1, "grid_resolution_m": 10})
        model["requirements"][0]["threshold"] = 50
        return normalize(model)

    def test_swept_segment_avoids_missing_coverage_between_samples(self):
        result = evaluate(self.model(), {"UAV_1": [{"t": 0, "x": 5, "y": 0}, {"t": 10, "x": 5, "y": 20}]})
        self.assertEqual(result["metrics"]["coverage_pct"], 50)
        self.assertEqual(result["metrics"]["total_distance_m"], 20)
        self.assertEqual(result["metrics"]["coverage_threshold_time_s"], 10)

    def test_not_reached_time_stays_null(self):
        config = self.model()
        config["requirements"][0]["threshold"] = 95
        result = evaluate(config, {"UAV_1": [{"t": 0, "x": 5, "y": 0}, {"t": 10, "x": 5, "y": 20}]})
        self.assertIsNone(result["metrics"]["coverage_threshold_time_s"])
        self.assertEqual(result["requirements"][1]["status"], "fail")

    def test_overlap_counts_area_once(self):
        route = [{"t": 0, "x": 5, "y": 0}, {"t": 10, "x": 5, "y": 20}]
        result = evaluate(self.model(), {"UAV_1": route, "UAV_2": route})
        self.assertEqual(result["metrics"]["coverage_pct"], 50)
        self.assertEqual(result["metrics"]["overlap_between_members_pct"], 50)

    def test_difference_points_and_zero_denominator(self):
        rows = compare_metrics({"coverage_pct": 90, "total_distance_m": 0}, {"coverage_pct": 94, "total_distance_m": 2})
        self.assertEqual(rows[0]["delta"], 4)
        self.assertAlmostEqual(rows[0]["relative_change_pct"], 4 / 90 * 100)
        self.assertIsNone(rows[2]["relative_change_pct"])

    def test_segment_clamps_to_endpoints(self):
        self.assertEqual(segment_distance_sq(15, 0, {"x": 0, "y": 0}, {"x": 10, "y": 0}), 25)

    def test_coordinate_roundtrip(self):
        for origin in ((30, 110), (-45, -70)):
            lat, lon = xy_to_geo(500, -200, origin)
            latitude, longitude = math.radians(lat), math.radians(lon)
            n = EARTH_A / math.sqrt(1 - EARTH_E2 * math.sin(latitude) ** 2)
            position = {"x": (n + 300) * math.cos(latitude) * math.cos(longitude),
                        "y": (n + 300) * math.cos(latitude) * math.sin(longitude),
                        "z": (n * (1 - EARTH_E2) + 300) * math.sin(latitude)}
            x, y = ecef_to_xy(position, origin)
            self.assertAlmostEqual(x, 500, places=5)
            self.assertAlmostEqual(y, -200, places=5)


class FailureEvidence(unittest.TestCase):
    def test_engine_failures_remain_in_comparison(self):
        model = read_json(PROJECT_ROOT / "examples/coverage_project.json")
        with test_directory() as temp:
            with patch("workbench.experiment.run_mission", side_effect=RuntimeError("injected_engine_failure")):
                result = run_comparison(model, temp)
            self.assertEqual(result["comparison"]["status"], "incomplete")
            self.assertEqual(len(result["comparison"]["runs"]), 2)
            self.assertTrue(all(r["status"] == "failed" for r in result["comparison"]["runs"]))
            self.assertEqual(result["comparison"]["differences"], [])
            self.assertTrue(Path(result["preview"]).is_file())


if __name__ == "__main__":
    unittest.main()
