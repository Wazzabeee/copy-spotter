"""Build the copy-spotter web app into a static site, and optionally serve it for local testing.

The site runs copy-spotter in the browser with Pyodide. Everything it loads is copied into the output
directory, so the deployed page makes no request to another host:

- the Pyodide runtime (pinned version, files checked against pinned sha256 hashes);
- the Pyodide packages copy-spotter needs (cryptography for pdfminer, ...), checked against the hashes of the
  pinned ``pyodide-lock.json``;
- the copy-spotter wheel built from this checkout;
- the wheels of the dependencies Pyodide does not ship (pdfminer.six, odfpy, defusedxml), at the versions and
  hashes of ``uv.lock``. odfpy only publishes an sdist, so pip builds a pure Python wheel from it.

Usage (from the repository root)::

    uv run python web/build.py              # build into web/_site
    uv run python web/build.py --serve      # build, then serve on http://localhost:8000

Downloads are cached in ``web/.cache``. Needs ``uv`` and network access to jsDelivr and PyPI.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

PYODIDE_VERSION = "314.0.8"
PYODIDE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
# sha256 of the runtime files, identical in the jsDelivr distribution and the `pyodide` npm package.
PYODIDE_CORE = {
    "pyodide.mjs": "1bb8cc14f9405aaa7cd4e00c12edd0a8539de9cc026618d6ee5a9663f367dc70",
    "pyodide.asm.mjs": "22514b8be6980e28a02c8b1d6387ce8dfe666fc4edf8d547cff5dce29ff4d972",
    "pyodide.asm.wasm": "e14d49ceca9b4a0e274ea918f3a898de2d3880b6e5573a6cfe1a2267ecc70329",
    "python_stdlib.zip": "2bd3394a145bfbbe5bbc9d9d6ab9136abbb986c6fef6c142b3a2962227aa5c28",
    "pyodide-lock.json": "5dc2fc119108bc148c7457dc86e7675b5c87e1cafd420b9c34c1eaef7b36c010",
}
# Requirements of copy-spotter that Pyodide ships, plus micropip; their dependencies are added from the lock.
PYODIDE_PACKAGES = ("micropip", "cryptography", "charset-normalizer", "tqdm")
# Requirements Pyodide does not ship: their wheels come from PyPI at the versions pinned in uv.lock.
PYPI_PACKAGES = ("pdfminer-six", "odfpy", "defusedxml")
PYPI_INDEX = "https://pypi.org/simple"

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
CACHE = WEB / ".cache"
SITE_FILES = ("index.html", "app.css", "app.js", "worker.js", "copy_spotter_web.py")
SAMPLES = ROOT / "data" / "pdf" / "plagiarism"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, dest: Path, expected_sha256: str) -> None:
    """Download ``url`` to ``dest`` unless a cached copy with the expected hash is there."""
    if dest.is_file() and sha256(dest) == expected_sha256:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256:
        raise SystemExit(f"sha256 mismatch for {url}: expected {expected_sha256}, got {actual}")
    dest.write_bytes(data)


def pyodide_closure(lock: dict[str, object]) -> list[dict[str, str]]:
    """Return the lock entries of PYODIDE_PACKAGES and of everything they depend on."""
    packages: dict[str, dict[str, object]] = lock["packages"]  # type: ignore[assignment]
    todo, seen = list(PYODIDE_PACKAGES), set[str]()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(packages[name]["depends"])  # type: ignore[arg-type]
    return [packages[name] for name in sorted(seen)]  # type: ignore[misc]


def copy_pyodide(out: Path) -> list[str]:
    """Copy the Pyodide runtime and the needed packages into ``out``; return the package names to load."""
    out.mkdir(parents=True)
    for name, digest in PYODIDE_CORE.items():
        fetch(PYODIDE_URL + name, CACHE / "pyodide" / name, digest)
        shutil.copy2(CACHE / "pyodide" / name, out / name)
    lock = json.loads((out / "pyodide-lock.json").read_text(encoding="utf-8"))
    names = []
    for entry in pyodide_closure(lock):
        fetch(PYODIDE_URL + entry["file_name"], CACHE / "pyodide" / entry["file_name"], entry["sha256"])
        shutil.copy2(CACHE / "pyodide" / entry["file_name"], out / entry["file_name"])
        names.append(entry["name"])
    return names


def run(command: list[str]) -> str:
    print("+", " ".join(command))
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, cwd=ROOT).stdout


def pypi_requirements() -> str:
    """Return the hashed requirements of PYPI_PACKAGES, exported from uv.lock."""
    exported = run(["uv", "export", "--no-config", "--locked", "--no-dev", "--no-emit-project", "--no-header"])
    blocks = exported.replace("\\\n", " ").splitlines()
    wanted = [line for line in blocks if line.split("==")[0].strip().lower() in PYPI_PACKAGES]
    found = {line.split("==")[0].strip().lower() for line in wanted}
    if found != set(PYPI_PACKAGES):
        raise SystemExit(f"uv.lock does not pin {sorted(set(PYPI_PACKAGES) - found)}")
    return "\n".join(wanted) + "\n"


def build_wheels(out: Path) -> list[str]:
    """Build copy-spotter and fetch or build its PyPI-only dependencies into ``out``; return the file names."""
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as tmp:
        run(["uv", "build", "--no-config", "--wheel", "--out-dir", tmp])
        requirements = Path(tmp) / "requirements.txt"
        requirements.write_text(pypi_requirements(), encoding="utf-8")
        run(
            [
                "uvx",
                "--no-config",
                "--index-url",
                PYPI_INDEX,
                "pip",
                "wheel",
                "--quiet",
                "--no-deps",
                "--require-hashes",
                "--index-url",
                PYPI_INDEX,
                "--wheel-dir",
                tmp,
                "--requirement",
                str(requirements),
            ]
        )
        wheels = sorted(Path(tmp).glob("*.whl"))
        for wheel in wheels:
            if not wheel.name.endswith("-none-any.whl"):
                raise SystemExit(f"{wheel.name} is not a pure Python wheel: Pyodide cannot install it")
            shutil.copy2(wheel, out / wheel.name)
    names = [wheel.name for wheel in wheels]
    if not any(name.startswith("copy_spotter-") for name in names) or len(names) != len(PYPI_PACKAGES) + 1:
        raise SystemExit(f"unexpected wheels: {names}")
    return names


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    packages = copy_pyodide(out / "pyodide")
    wheels = build_wheels(out / "wheels")
    for name in SITE_FILES:
        shutil.copy2(WEB / name, out / name)
    size = sum(path.stat().st_size for path in out.rglob("*") if path.is_file())
    manifest = {
        "pyodide": PYODIDE_VERSION,
        "packages": packages,
        "wheels": wheels,
        "download_mb": round(size / 1e6, 1),  # shown on the page: everything a first visit downloads
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built {out} ({size / 1e6:.1f} MB): Pyodide {PYODIDE_VERSION}, packages {packages}, wheels {wheels}")


class DevHandler(http.server.SimpleHTTPRequestHandler):
    """Serve the site with the right module and wasm types, plus the sample documents under /_dev/samples/."""

    extensions_map = {  # noqa: RUF012 (same shape as the base class attribute)
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".wasm": "application/wasm",
        ".json": "application/json",
    }

    def translate_path(self, path: str) -> str:
        prefix = "/_dev/samples/"
        if path.startswith(prefix):
            name = Path(path[len(prefix) :].split("?", maxsplit=1)[0]).name
            return str(SAMPLES / name) if name else str(SAMPLES)
        return super().translate_path(path)


def serve(site: Path, port: int) -> None:
    handler = functools.partial(DevHandler, directory=str(site))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Serving {site} on http://localhost:{port}/ (samples under /_dev/samples/)")
        server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=WEB / "_site", help="output directory (default: web/_site)")
    parser.add_argument("--serve", action="store_true", help="serve the site after building it")
    parser.add_argument("--no-build", action="store_true", help="serve the existing build without rebuilding")
    parser.add_argument("--port", type=int, default=8000, help="port of --serve (default: 8000)")
    args = parser.parse_args()
    out = args.out.resolve()
    if not args.no_build:
        build(out)
    if args.serve or args.no_build:
        serve(out, args.port)


if __name__ == "__main__":
    main()
