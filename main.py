"""Compatibility launcher; the command implementation lives in workbench.cli."""

from workbench.cli import main, run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli())
