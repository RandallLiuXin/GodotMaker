#!/usr/bin/env python3
"""Interpreter-scoped discovery for the `godot-e2e` Python package.

Godot E2E ships in two independent halves:

* the **Godot addon** `addons/godot_e2e/` inside the game project
  (checked by `tools/check_project.py`), and
* the **Python package** `godot-e2e` (import name `godot_e2e`, console
  script `godot-e2e`) installed into a Python environment.

Only the second half is this module's business. The failure it exists to
remove is the pipeline asking PATH for a bare `godot-e2e` command: PATH
answers for whichever environment happens to come first, which is not
necessarily the interpreter the rest of the verification flow runs on.
When the two disagree the user is told `godot-e2e` is missing while the
package is installed and visible somewhere else, and nothing in the
message names the environment that was actually consulted.

So discovery here is anchored to one interpreter, that interpreter is
named in every diagnostic, and the suite is launched through it
(`<interpreter> -m godot_e2e.cli`) instead of through PATH.

Every call re-probes. Nothing is memoized at module or process level, so
a run that follows a corrected interpreter, virtualenv or install sees
the corrected state instead of an earlier "missing" verdict.

Usage:
    python tools/e2e_env.py            # human-readable report
    python tools/e2e_env.py --json     # machine-readable report

Exit codes:
    0   the package is importable by the target interpreter
    1   it is not (missing, broken, or installed in another environment)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Distribution name on PyPI, import name, and the module behind the
# `godot-e2e` console script (declared as `godot-e2e = "godot_e2e.cli:main"`
# in the package's pyproject). `godot_e2e.cli` guards its `main()` with a
# `__main__` block, so `-m godot_e2e.cli` is a supported entry point.
PACKAGE_NAME = "godot-e2e"
IMPORT_NAME = "godot_e2e"
CLI_MODULE = "godot_e2e.cli"
CLI_EXECUTABLES = ("godot-e2e", "godot-e2e.exe", "godot-e2e.cmd", "godot-e2e.bat")

PROBE_TIMEOUT = 60

# Status values, ordered from healthy to broken.
STATUS_OK = "ok"                                # importable by the target interpreter
STATUS_IMPORT_ERROR = "import_error"            # installed there but `import` raises
STATUS_OTHER_ENVIRONMENT = "other_environment"  # missing here, CLI found elsewhere
STATUS_MISSING = "missing"                      # not installed anywhere we can see
STATUS_PROBE_FAILED = "probe_failed"            # the interpreter could not be questioned

# Executed by the *target* interpreter, not by this one — keep it to the
# standard library and to syntax valid on the oldest interpreter the
# package supports (3.9).
_PROBE_SOURCE = r"""
import json
import sys
import sysconfig


def _scripts_dirs():
    dirs = []
    for scheme in (None, "user"):
        try:
            if scheme is None:
                path = sysconfig.get_path("scripts")
            else:
                path = sysconfig.get_path(
                    "scripts", sysconfig.get_preferred_scheme(scheme)
                )
        except Exception:
            continue
        if path and path not in dirs:
            dirs.append(path)
    return dirs


info = {
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": getattr(sys, "base_prefix", sys.prefix),
    "python_version": "%d.%d.%d" % sys.version_info[:3],
    "scripts_dirs": _scripts_dirs(),
    "installed": False,
    "location": None,
    "import_error": None,
    "dist_version": None,
    "cli_module": False,
}

try:
    from importlib import metadata as _metadata
    info["dist_version"] = _metadata.version("godot-e2e")
except Exception:
    pass

try:
    import godot_e2e
    info["installed"] = True
    info["location"] = getattr(godot_e2e, "__file__", None)
except Exception as exc:
    info["import_error"] = "%s: %s" % (type(exc).__name__, exc)

if info["installed"]:
    try:
        import importlib.util
        info["cli_module"] = importlib.util.find_spec("godot_e2e.cli") is not None
    except Exception:
        info["cli_module"] = False

print(json.dumps(info))
"""


def _same_dir(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(
        os.path.normpath(right)
    )


def quote_arg(value: str) -> str:
    """Quote a single command argument for display / copy-paste."""
    return f'"{value}"' if any(c.isspace() for c in value) else value


def format_command(command: list[str] | None) -> str | None:
    """Render a command list as a copy-pasteable one-liner."""
    if not command:
        return None
    return " ".join(quote_arg(part) for part in command)


@dataclass(frozen=True)
class E2EPythonEnv:
    """What one interpreter can tell us about the `godot-e2e` package."""

    interpreter: str
    status: str
    prefix: str | None = None
    base_prefix: str | None = None
    python_version: str | None = None
    virtual_env: str | None = None
    package_version: str | None = None
    package_location: str | None = None
    import_error: str | None = None
    probe_error: str | None = None
    cli_path: str | None = None
    cli_in_target_env: bool = False
    cli_module: bool = False
    scripts_dirs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def available(self) -> bool:
        """True when the target interpreter can import the package."""
        return self.status == STATUS_OK

    @property
    def in_virtual_env(self) -> bool:
        return bool(self.prefix and self.base_prefix and self.prefix != self.base_prefix)

    @property
    def virtual_env_mismatch(self) -> bool:
        """An activated virtualenv that does not own the target interpreter.

        The activated environment is what the user believes they installed
        into, so it belongs in the diagnostic even though the verdict is
        decided by `interpreter`.
        """
        if not self.virtual_env:
            return False
        try:
            Path(self.interpreter).resolve().relative_to(
                Path(self.virtual_env).resolve()
            )
        except (ValueError, OSError):
            return True
        return False

    @property
    def run_command(self) -> list[str] | None:
        """How to launch the suite through the interpreter we verified."""
        if not self.available:
            return None
        if self.cli_module:
            return [self.interpreter, "-m", CLI_MODULE]
        if self.cli_path and self.cli_in_target_env:
            return [self.cli_path]
        return None

    @property
    def install_command(self) -> list[str]:
        return [self.interpreter, "-m", "pip", "install", PACKAGE_NAME]

    def summary(self) -> str:
        """One line, always naming the interpreter that was consulted."""
        version = f" {self.package_version}" if self.package_version else ""
        if self.status == STATUS_OK:
            return (
                f"Python package '{PACKAGE_NAME}'{version} available to "
                f"{self.interpreter}"
            )
        if self.status == STATUS_IMPORT_ERROR:
            return (
                f"Python package '{PACKAGE_NAME}'{version} is installed for "
                f"{self.interpreter} but fails to import: {self.import_error}"
            )
        if self.status == STATUS_OTHER_ENVIRONMENT:
            return (
                f"Python package '{PACKAGE_NAME}' missing for {self.interpreter}; "
                f"a godot-e2e command exists at {self.cli_path} but belongs to "
                "another Python environment"
            )
        if self.status == STATUS_PROBE_FAILED:
            return (
                f"Could not query {self.interpreter} for the '{PACKAGE_NAME}' "
                f"Python package: {self.probe_error}"
            )
        return f"Python package '{PACKAGE_NAME}' missing for {self.interpreter}"

    def diagnostic_lines(self) -> list[str]:
        """Environment facts plus the next action."""
        lines = [f"interpreter: {self.interpreter}"]
        if self.python_version:
            lines.append(f"python version: {self.python_version}")
        if self.prefix:
            suffix = " (virtualenv)" if self.in_virtual_env else ""
            lines.append(f"sys.prefix: {self.prefix}{suffix}")
        lines.append(f"VIRTUAL_ENV: {self.virtual_env or 'not set'}")
        if self.virtual_env_mismatch:
            lines.append(
                f"VIRTUAL_ENV {self.virtual_env} does not contain "
                f"{self.interpreter} — the activated environment is not the "
                "one this check used"
            )
        lines.append(f"godot-e2e command on PATH: {self.cli_path or 'not found'}")
        if self.package_location:
            lines.append(f"package location: {self.package_location}")

        if self.status == STATUS_OK:
            command = format_command(self.run_command)
            if command:
                lines.append(f"run the suite with: {command} e2e/ -v")
            return lines

        if self.status == STATUS_OTHER_ENVIRONMENT:
            lines.append(
                f"the godot-e2e command at {self.cli_path} is not part of "
                f"{self.interpreter}; either install the package into that "
                "interpreter or run the verification flow with the interpreter "
                "that owns the command"
            )
        elif self.status == STATUS_IMPORT_ERROR:
            lines.append(f"import error: {self.import_error}")
        elif self.status == STATUS_MISSING and self.cli_in_target_env:
            lines.append(
                "a godot-e2e command exists in this interpreter's scripts "
                "directory but the package does not import — reinstall it"
            )
        lines.append(f"next: {format_command(self.install_command)}")
        return lines

    def report(self) -> str:
        body = [f"  {line}" for line in self.diagnostic_lines()]
        return "\n".join([self.summary(), *body])

    def to_dict(self) -> dict:
        return {
            "interpreter": self.interpreter,
            "status": self.status,
            "available": self.available,
            "prefix": self.prefix,
            "base_prefix": self.base_prefix,
            "python_version": self.python_version,
            "virtual_env": self.virtual_env,
            "virtual_env_mismatch": self.virtual_env_mismatch,
            "package": PACKAGE_NAME,
            "package_version": self.package_version,
            "package_location": self.package_location,
            "import_error": self.import_error,
            "probe_error": self.probe_error,
            "cli_path": self.cli_path,
            "cli_in_target_env": self.cli_in_target_env,
            "scripts_dirs": list(self.scripts_dirs),
            "run_command": self.run_command,
            "install_command": self.install_command,
            "summary": self.summary(),
            "diagnostics": self.diagnostic_lines(),
        }


def resolve_interpreter(interpreter: str | None = None) -> str:
    """The interpreter the verification flow speaks for.

    `sys.executable` — the interpreter running this tool — and never a
    guess reconstructed from `VIRTUAL_ENV` or PATH. An activated
    environment that does not own it is reported as a mismatch instead of
    silently taking over, because switching interpreters here would hide
    the very confusion this module exists to expose.
    """
    return interpreter or sys.executable


def find_cli(env: dict[str, str] | None = None) -> str | None:
    """Locate a `godot-e2e` console script on PATH, if any."""
    path = (env if env is not None else os.environ).get("PATH")
    for name in CLI_EXECUTABLES:
        found = shutil.which(name, path=path)
        if found:
            return found
    return None


def _run_probe(interpreter: str) -> tuple[dict | None, str | None]:
    try:
        proc = subprocess.run(
            [interpreter, "-c", _PROBE_SOURCE],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=PROBE_TIMEOUT,
        )
    except FileNotFoundError:
        return None, f"interpreter not found at {interpreter!r}"
    except subprocess.TimeoutExpired:
        return None, f"probe timed out after {PROBE_TIMEOUT}s"
    except OSError as exc:
        return None, f"probe could not start: {exc}"

    stdout = (proc.stdout or "").strip()
    if not stdout:
        detail = (proc.stderr or "").strip().splitlines()
        return None, (
            detail[-1] if detail
            else f"probe exited {proc.returncode} with no output"
        )
    try:
        # The probe prints exactly one JSON line; whatever a sitecustomize
        # or a startup banner printed before it is not ours.
        return json.loads(stdout.splitlines()[-1]), None
    except (ValueError, IndexError):
        return None, "probe returned malformed JSON"


def probe_e2e_python_env(
    interpreter: str | None = None,
    env: dict[str, str] | None = None,
) -> E2EPythonEnv:
    """Ask one interpreter whether it can use the `godot-e2e` package.

    Always re-runs the probe — see the module docstring on why this must
    not be cached.
    """
    target = resolve_interpreter(interpreter)
    environ = env if env is not None else os.environ
    virtual_env = environ.get("VIRTUAL_ENV") or None
    cli_path = find_cli(environ)

    info, probe_error = _run_probe(target)
    if info is None:
        return E2EPythonEnv(
            interpreter=target,
            status=STATUS_PROBE_FAILED,
            virtual_env=virtual_env,
            probe_error=probe_error,
            cli_path=cli_path,
        )

    scripts_dirs = tuple(str(d) for d in info.get("scripts_dirs") or ())
    cli_in_target_env = bool(
        cli_path and any(_same_dir(str(Path(cli_path).parent), d) for d in scripts_dirs)
    )

    installed = bool(info.get("installed"))
    if installed:
        status = STATUS_OK
    elif info.get("dist_version"):
        # The distribution is registered for this interpreter, so this is a
        # broken install rather than an absent one.
        status = STATUS_IMPORT_ERROR
    elif cli_path and not cli_in_target_env:
        status = STATUS_OTHER_ENVIRONMENT
    else:
        status = STATUS_MISSING

    return E2EPythonEnv(
        interpreter=info.get("executable") or target,
        status=status,
        prefix=info.get("prefix"),
        base_prefix=info.get("base_prefix"),
        python_version=info.get("python_version"),
        virtual_env=virtual_env,
        package_version=info.get("dist_version"),
        package_location=info.get("location"),
        import_error=info.get("import_error"),
        cli_path=cli_path,
        cli_in_target_env=cli_in_target_env,
        cli_module=bool(info.get("cli_module")),
        scripts_dirs=scripts_dirs,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Report whether the godot-e2e Python package is available to the "
            "interpreter the verification flow uses."
        )
    )
    parser.add_argument(
        "--python",
        dest="interpreter",
        default=None,
        help="Probe this interpreter instead of the one running this script.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    info = probe_e2e_python_env(args.interpreter)
    if args.json:
        print(json.dumps(info.to_dict(), indent=2))
    else:
        print(info.report())
    return 0 if info.available else 1


if __name__ == "__main__":
    sys.exit(main())
