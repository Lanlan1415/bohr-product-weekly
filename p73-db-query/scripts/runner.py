"""Controlled execution for code produced by this package's generator only."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def _sanitized_environment():
    """Do not forward credentials, proxy variables, or caller Python state."""
    env = {
        "PATH": str(Path(sys.executable).resolve().parent),
        "PYTHONHASHSEED": "0",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_PROXY": "*",
    }
    for key in ("SYSTEMROOT", "WINDIR", "LC_ALL", "LANG"):
        if key in os.environ and key in ("SYSTEMROOT", "WINDIR"):
            env[key] = os.environ[key]
    return env


def _read_capped(path, max_chars):
    if not path.exists():
        return "", False
    # UTF-8 needs at most four bytes per character.  Never load an unbounded log.
    byte_cap = max_chars * 4 + 4
    with path.open("rb") as handle:
        data = handle.read(byte_cap + 1)
    truncated = len(data) > byte_cap or path.stat().st_size > len(data)
    text = data[:byte_cap].decode("utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    return text, truncated


def execute_generated(code_path, out_dir, timeout=20, max_output_chars=4000):
    """Run one generated file without a shell; return an execution record.

    The function intentionally has no command/string parameter.  It is not a
    general-purpose sandbox: callers must pass code emitted and audited by
    codegen.generate_code.  Network/credential APIs are outside that generator's
    grammar, and this process environment carries no caller secrets.
    """
    code_path = Path(code_path).resolve()
    out_dir = Path(out_dir).resolve()
    timeout = max(1, min(int(timeout), 120))
    max_output_chars = max(100, min(int(max_output_chars), 50000))
    stdout_path = out_dir / ".scicode-stdout.tmp"
    stderr_path = out_dir / ".scicode-stderr.tmp"
    command = [sys.executable, "-I", "-B", str(code_path)]
    started = time.monotonic()
    returncode, timed_out, spawn_error = None, False, None
    try:
        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                command, cwd=str(out_dir), env=_sanitized_environment(), shell=False,
                stdin=subprocess.DEVNULL, stdout=stdout_handle, stderr=stderr_handle)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                returncode = process.wait(timeout=5)
    except OSError as exc:
        spawn_error = f"{type(exc).__name__}: {str(exc)[:300]}"
    duration_ms = round((time.monotonic() - started) * 1000, 3)
    stdout, stdout_truncated = _read_capped(stdout_path, max_output_chars)
    stderr, stderr_truncated = _read_capped(stderr_path, max_output_chars)
    for path in (stdout_path, stderr_path):
        try:
            path.unlink()
        except OSError:
            pass
    executed = spawn_error is None and not timed_out and returncode in (0, 3, 4, 5)
    record = {
        "schema_version": "scicode-execution/v1",
        "execution_attempted": True,
        "executed": executed,
        "exit_code": returncode,
        "timed_out": timed_out,
        "command": ["python", "-I", "-B", "analysis.py"],
        "shell": False,
        "isolated_python": True,
        "timeout_seconds": timeout,
        "output_char_limit": max_output_chars,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "spawn_error": spawn_error,
    }
    log = dict(record)
    log["duration_ms"] = duration_ms
    log["interpreter"] = sys.executable
    log["environment_policy"] = "minimal fixed environment; caller credentials and proxy variables not forwarded"
    (out_dir / "execution-log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    return record
