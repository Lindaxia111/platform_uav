"""Check project structure, source syntax, local links, tests and engine setup."""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    ".editorconfig", ".gitattributes", ".gitignore", "AGENTS.md", "README.md",
    "SESSION_HANDOFF.md", "main.py", "启动平台.cmd", "一键验证.cmd", "检查项目.cmd",
}
PROJECT_DIRECTORIES = {"workbench", "algorithms", "examples", "tests", "docs", "scripts"}
ROOT_DIRECTORIES = PROJECT_DIRECTORIES | {
    "artifacts", ".git", ".venv", ".vscode", ".idea", ".agents", ".codex", ".aws",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
REQUIRED_FILES = ROOT_FILES | {
    "workbench/cli.py", "workbench/__main__.py", "examples/coverage_project.json",
    "examples/results/latest.json", "docs/DEVELOPMENT.md", "docs/ARCHITECTURE.md",
    "docs/AFSIM_GUIDE.md", "docs/原型验证记录.md", "docs/STRUCTURE_CHANGELOG.md",
}


class LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.links.append(value)


def check_structure():
    errors = []
    for entry in PROJECT_ROOT.iterdir():
        allowed = ROOT_DIRECTORIES if entry.is_dir() else ROOT_FILES
        if entry.name not in allowed:
            errors.append(f"根目录未登记条目：{entry.name}；请按 docs/DEVELOPMENT.md 归类")
    for directory in sorted(PROJECT_DIRECTORIES):
        if not (PROJECT_ROOT / directory).is_dir():
            errors.append(f"缺少目录：{directory}")
    for filename in sorted(REQUIRED_FILES):
        if not (PROJECT_ROOT / filename).is_file():
            errors.append(f"缺少文件：{filename}")
    sources = [PROJECT_ROOT / "main.py"]
    for folder in ("workbench", "algorithms", "tests", "scripts"):
        sources.extend((PROJECT_ROOT / folder).rglob("*.py"))
    for source in sources:
        try:
            ast.parse(source.read_text(encoding="utf-8-sig"), filename=str(source))
        except (OSError, UnicodeError, SyntaxError) as error:
            errors.append(f"Python 文件无效：{source.relative_to(PROJECT_ROOT)}：{error}")
    json_files = [PROJECT_ROOT / "examples/coverage_project.json"]
    json_files.extend((PROJECT_ROOT / "algorithms").glob("*/manifest.json"))
    for filename in json_files:
        try:
            json.loads(filename.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as error:
            errors.append(f"JSON 文件无效：{filename.relative_to(PROJECT_ROOT)}：{error}")
    markdown = list(PROJECT_ROOT.glob("*.md")) + list((PROJECT_ROOT / "docs").rglob("*.md"))
    for filename in markdown:
        content = filename.read_text(encoding="utf-8-sig")
        for link in re.findall(r"\[[^\]\n]*\]\(([^)\n]+)\)", content):
            check_local_link(filename, link.strip("<>"), errors)
    check_demo(errors)
    return errors


def check_local_link(source, link, errors):
    parsed = urlsplit(link)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return
    target = (source.parent / unquote(parsed.path)).resolve()
    if not target.is_relative_to(PROJECT_ROOT) or not target.exists():
        errors.append(f"本地链接无效：{source.relative_to(PROJECT_ROOT)} -> {link}")


def check_demo(errors):
    index_file = PROJECT_ROOT / "examples/results/latest.json"
    try:
        index = json.loads(index_file.read_text(encoding="utf-8-sig"))
        resolved = {}
        for key in ("directory", "preview"):
            value = index[key]
            if not isinstance(value, str) or Path(value).is_absolute():
                raise ValueError(f"{key} 必须是相对于 latest.json 的路径")
            target = (index_file.parent / value).resolve()
            if not target.is_relative_to(index_file.parent) or not target.exists():
                raise ValueError(f"{key} 指向不存在或越界的位置：{value}")
            resolved[key] = target
        if not resolved["directory"].is_dir() or resolved["preview"].parent != resolved["directory"]:
            raise ValueError("演示目录与预览位置不一致")
        parser = LocalLinks()
        parser.feed(resolved["preview"].read_text(encoding="utf-8"))
        for link in parser.links:
            check_local_link(resolved["preview"], link, errors)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        errors.append(f"演示索引或预览无效：{error}")


def main():
    parser = argparse.ArgumentParser(description="验证目录规范、源码、链接、测试和默认模型")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--static-only", action="store_true", help="只检查目录、语法、JSON 和本地链接")
    modes.add_argument("--with-afsim", action="store_true", help="额外执行真实 AFSIM A/B 比较")
    args = parser.parse_args()
    errors = check_structure()
    if errors:
        for error in errors:
            print(f"[失败] {error}")
        return 1
    print("[通过] 目录规范、Python 语法、JSON、文档链接和演示证据链接", flush=True)
    if args.static_only:
        return 0
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    log_dir = PROJECT_ROOT / "artifacts" / "verification" / run_id
    log_dir.mkdir(parents=True)
    environment = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    python = [sys.executable, "-X", "utf8", "-B"]
    steps = [
        ("tests", "全部单元与隐藏界面测试", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("model", "默认工程模型与本机引擎配置", ["-m", "workbench", "check"]),
        ("legacy_entry", "原 main.py 入口兼容性", ["main.py", "check"]),
    ]
    if args.with_afsim:
        steps.append(("afsim", "真实 AFSIM A/B 比较", [
            "-m", "workbench", "compare", "--output-root", str(PROJECT_ROOT / "artifacts/runs"),
        ]))
    failed = False
    for name, label, arguments in steps:
        log_path = log_dir / f"{name}.log"
        print(f"[执行] {label}", flush=True)
        try:
            with log_path.open("wb") as stream:
                process = subprocess.run(
                    python + arguments, cwd=PROJECT_ROOT, env=environment,
                    stdout=stream, stderr=subprocess.STDOUT, timeout=300,
                )
            if process.returncode:
                failed = True
                print(f"[失败] {label}；详见 {log_path}")
                print(log_path.read_text(encoding="utf-8", errors="replace")[-5000:])
            else:
                print(f"[通过] {label}", flush=True)
        except (OSError, subprocess.TimeoutExpired) as error:
            failed = True
            print(f"[失败] {label}：{error}；详见 {log_path}")
    print(f"验证日志：{log_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
