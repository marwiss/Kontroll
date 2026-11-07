# This file was generated with the assistance of an AI coding tool.
"""Install the environment buildingSMART's ifc-gherkin-rules run in: ``python -m opencde.ifcgraph.gherkin_install TARGET``.

ADR 0012. The rule set is run as its own tests run it, with behave 1.2.6 and IfcOpenShell 0.8.6, which is what its CI
uses; Kontroll itself keeps IfcOpenShell 0.9, which one of the rule set's helpers does not work with. So the rules get a
virtual environment of their own, made here from pinned artifacts, each checked against its SHA-256 before use:

* the rule set at a fixed commit, of which only ``features/``, the JSON formatter, ``behave.ini`` and the licence are kept;
* ``dataclass_compat.py`` and the licence of buildingSMART's data model: the result codes, without Django;
* IfcOpenShell's own build of 0.8.6 for this platform, unpacked into the environment as the rule set's CI does;
* the packages of ``gherkin-requirements.txt``, installed with their hashes.

Two files of Kontroll's own (``gherkin_shim/``) take the place of the rule set's ``validation_results.py`` and
``features/environment.py``, which would set up Django and its database. Uses only the standard library and ``uv`` or
``pip``, so that a Docker build can run it.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess  # nosec B404 - uv, pip and the new interpreter, with fixed arguments
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

RULES_COMMIT = "893f8275049b8960c3ce0c7379b4b57aefeaa8f9"
MODELS_COMMIT = "cad20d3f67728fb53b7e65fe8eb903a9ad28f412"
IFCOPENSHELL = "0.8.6-8b5b400"

_MODELS = f"https://raw.githubusercontent.com/buildingSMART/ifc-validation-data-model/{MODELS_COMMIT}"
_BUILDS = "https://s3.amazonaws.com/ifcopenshell-builds"
RULES = (
    f"https://codeload.github.com/buildingSMART/ifc-gherkin-rules/tar.gz/{RULES_COMMIT}",
    "2b65cc3cf3ba75f05a7908e32300e849d74e8f28d618eaadbc2bfc41f585461b",
)
DATACLASS_COMPAT = (
    f"{_MODELS}/dataclass_compat.py",
    "76c61481b57a412a6a3718027b2dbc870e33ed0f47bd9482a575adf1e2e4af3b",
)
MODELS_LICENSE = (f"{_MODELS}/LICENSE", "d7e4fadc1737360cb2c7b019d1bb5ce33acd46cc8b3f76bf9dca7ac065e60283")
IFCOPENSHELL_BUILDS = {
    ("Linux", "x86_64"): (
        f"{_BUILDS}/ifcopenshell-python-313-v{IFCOPENSHELL}-linux64.zip",
        "5001cac127607fdbee88960c0a4b08f2bfe26af6e13754fb15fb432d64e98da7",
    ),
    ("Linux", "aarch64"): (
        f"{_BUILDS}/ifcopenshell-python-313-v{IFCOPENSHELL}-linuxarm64.zip",
        "b105664fe942c41232f9f25153ddc26e28e4352130fbe8d993de308389acbfc0",
    ),
    ("Windows", "AMD64"): (
        f"{_BUILDS}/ifcopenshell-python-313-v{IFCOPENSHELL}-win64.zip",
        "0bf0e564cffc585a6ea0ef6f6b46d42bfbe0608bff35b931f6d80071d163fa13",
    ),
}
KEPT = ("features/", "outcome_embedding_json_formatter.py", "behave.ini", "LICENSE")
MAX_DOWNLOAD = 200 * 1024 * 1024
HERE = Path(__file__).resolve().parent
MANIFEST = "manifest.json"


class InstallError(RuntimeError):
    """The environment could not be made as pinned."""


def fetch(url: str, sha256: str) -> bytes:
    """A pinned artifact, refused unless its SHA-256 is the one written here."""
    if not url.startswith("https://"):
        raise InstallError(f"only https is fetched, not {url}")
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310  # nosec B310 - https only, pinned by hash
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise InstallError(f"{url} is larger than {MAX_DOWNLOAD} bytes")
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        raise InstallError(f"{url} has SHA-256 {digest}, not the pinned {sha256}")
    return data


def _inside(root: Path, name: str) -> Path:
    """Where an archive member goes; a member that would leave ``root`` is refused."""
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if not parts or PurePosixPath(name).is_absolute() or ".." in parts or ":" in parts[0]:
        raise InstallError(f"refusing the archive member {name!r}")
    return root.joinpath(*parts)


def unpack_rules(data: bytes, run: Path) -> int:
    """The kept files of the rule set's archive, below its top folder. Returns how many."""
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts
            relative = "/".join(parts[1:])
            kept = any(relative == k or (k.endswith("/") and relative.startswith(k)) for k in KEPT)
            if len(parts) < 2 or not kept or not member.isfile():  # links and devices are never written
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            target = _inside(run, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read())
            count += 1
    return count


def unpack_ifcopenshell(data: bytes, site_packages: Path) -> int:
    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = _inside(site_packages, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            count += 1
    return count


def python_of(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(command: list[str]) -> str:
    done = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603  # nosec B603 - fixed commands
    if done.returncode != 0:
        raise InstallError(f"{Path(command[0]).name} failed: {(done.stderr or done.stdout).strip()[-500:]}")
    return done.stdout


def make_environment(venv: Path) -> Path:
    """A virtual environment with the pinned packages, made with uv where it is found and with pip otherwise."""
    requirements = str(HERE / "gherkin-requirements.txt")
    python = python_of(venv)
    uv = shutil.which("uv")
    if uv:
        _run([uv, "venv", "--quiet", "--python", sys.executable, str(venv)])
        _run([uv, "pip", "install", "--quiet", "--python", str(python), "--require-hashes", "-r", requirements])
    else:
        _run([sys.executable, "-m", "venv", str(venv)])
        _run([str(python), "-m", "pip", "install", "--quiet", "--require-hashes", "-r", requirements])
    return python


def install(target: Path) -> dict[str, str]:
    """Make the environment in ``target``, which must not exist or be empty. Returns the manifest written there."""
    build = IFCOPENSHELL_BUILDS.get((platform.system(), platform.machine()))
    if build is None:
        raise InstallError(
            f"no build of IfcOpenShell {IFCOPENSHELL} is pinned for {platform.system()} {platform.machine()}"
        )
    if sys.version_info[:2] != (3, 13):
        raise InstallError("the pinned build of IfcOpenShell is for Python 3.13")
    if target.exists() and any(target.iterdir()):
        raise InstallError(f"{target} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    venv, run = target / "venv", target / "run"
    python = make_environment(venv)
    site_packages = Path(
        _run([str(python), "-I", "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"]).strip()
    )
    unpack_ifcopenshell(fetch(*build), site_packages)
    unpack_rules(fetch(*RULES), run)
    shim = HERE / "gherkin_shim"
    (run / "features" / "environment.py").write_bytes((shim / "environment.py.in").read_bytes())
    (run / "validation_results.py").write_bytes((shim / "validation_results.py.in").read_bytes())
    models = run / "ifc_validation_models"
    models.mkdir()
    (models / "__init__.py").write_bytes(b"")
    (models / "dataclass_compat.py").write_bytes(fetch(*DATACLASS_COMPAT))
    (models / "LICENSE").write_bytes(fetch(*MODELS_LICENSE))
    _run([str(python), "-I", "-c", "import behave, ifcopenshell, numpy, pyproj, rtree, shapely"])
    manifest = {
        "rules_commit": RULES_COMMIT,
        "models_commit": MODELS_COMMIT,
        "ifcopenshell": IFCOPENSHELL,
        "ruleset": f"ifc-gherkin-rules {RULES_COMMIT[:7]} with IfcOpenShell {IFCOPENSHELL.split('-')[0]}",
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="opencde-gherkin-install", description=__doc__.split("\n", 1)[0])
    parser.add_argument("target", type=Path, help="an empty or missing folder")
    args = parser.parse_args(argv)
    try:
        manifest = install(args.target)
    except (InstallError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        sys.stderr.write(f"could not install: {exc}\n")
        return 1
    sys.stdout.write(f"installed {manifest['ruleset']} in {args.target}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
