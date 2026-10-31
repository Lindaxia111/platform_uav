"""Command-line interface shared by the package and compatibility launcher."""

import argparse
import json
import sys

from .experiment import PROJECT_ROOT, run_comparison
from .model import check_model, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="多无人机模块化建模与 AFSIM 验证原型")
    parser.add_argument("command", nargs="?", default="gui", choices=["gui", "check", "compare"])
    parser.add_argument("--model", default=str(PROJECT_ROOT / "examples" / "coverage_project.json"))
    parser.add_argument("--output-root")
    args = parser.parse_args(argv)
    if args.command == "gui":
        from .gui import launch
        launch(args.model)
        return 0
    model = read_json(args.model)
    if args.command == "check":
        issues = check_model(model, PROJECT_ROOT)
        print(json.dumps(issues, ensure_ascii=False, indent=2))
        return 1 if any(issue["level"] == "error" for issue in issues) else 0
    result = run_comparison(model, args.output_root, progress=print)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["comparison"]["status"] == "completed" else 1


def run_cli():
    try:
        return main()
    except Exception as error:
        print(f"执行失败：{error}", file=sys.stderr)
        return 1
