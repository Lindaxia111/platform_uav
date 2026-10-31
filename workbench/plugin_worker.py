"""Local subprocess boundary; this is not an untrusted-code security container."""

import contextlib
import importlib.util
import sys
from pathlib import Path

from .model import read_json, write_json
from .planning import package_info


def main():
    package, request_path, result_path = map(Path, sys.argv[1:4])
    info = package_info(package)
    filename, function = info["entrypoint"].split(":")
    sys.path.insert(0, str(package.resolve()))
    spec = importlib.util.spec_from_file_location("user_algorithm", package / filename)
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(sys.stderr):
        spec.loader.exec_module(module)
        result = getattr(module, function)(read_json(request_path))
    write_json(result_path, result)


if __name__ == "__main__":
    main()
