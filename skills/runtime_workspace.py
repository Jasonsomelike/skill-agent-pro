"""Isolated per-invocation workspace helpers for the agent strategy."""

from __future__ import annotations

import base64
import mimetypes
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


MAX_COMMAND_OUTPUT_CHARS = 30000
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024
EXPORTABLE_EXTENSIONS = {
    ".csv",
    ".docx",
    ".gif",
    ".html",
    ".jpeg",
    ".jpg",
    ".json",
    ".md",
    ".pdf",
    ".png",
    ".pptx",
    ".svg",
    ".txt",
    ".webp",
    ".xlsx",
    ".xml",
    ".zip",
}
MIME_TYPE_OVERRIDES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@dataclass(frozen=True)
class WorkspaceExport:
    relative_path: str
    absolute_path: Path
    filename: str
    mime_type: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.relative_path,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size": self.size,
        }


def _is_within_dir(base: Path, target: Path) -> bool:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    return base_resolved == target_resolved or base_resolved in target_resolved.parents


def safe_workspace_path(root: Path, relative_path: str, *, allow_root: bool = False) -> Path:
    root = root.resolve()
    raw = str(relative_path or "").strip().replace("\\", "/")
    if not raw or raw == ".":
        if allow_root:
            return root
        raise RuntimeError("relative_path is required")
    if raw.startswith("/"):
        raise RuntimeError("absolute paths are not allowed")

    target = (root / raw).resolve()
    if not _is_within_dir(root, target):
        raise RuntimeError("path escapes runtime workspace")
    if target == root and not allow_root:
        raise RuntimeError("relative_path must reference a workspace child")
    return target


def _bounded_file_limit(max_file_bytes: int) -> int:
    return max(1024, min(int(max_file_bytes or DEFAULT_MAX_FILE_BYTES), 100 * 1024 * 1024))


def write_workspace_file(
    root: Path,
    *,
    relative_path: str,
    content: str,
    encoding: str = "utf-8",
    append: bool = False,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    path = safe_workspace_path(root, relative_path)
    normalized_encoding = str(encoding or "utf-8").lower()
    if normalized_encoding in {"utf-8", "utf8", "text"}:
        data = str(content or "").encode("utf-8")
    elif normalized_encoding == "base64":
        try:
            data = base64.b64decode(str(content or ""), validate=True)
        except Exception as exc:
            raise RuntimeError(f"invalid base64 content: {exc}") from exc
    else:
        raise RuntimeError("encoding must be utf-8 or base64")

    max_bytes = _bounded_file_limit(max_file_bytes)
    existing_size = path.stat().st_size if append and path.is_file() else 0
    if existing_size + len(data) > max_bytes:
        raise RuntimeError(f"file exceeds runtime limit of {max_bytes} bytes")

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if append else "wb"
    with open(path, mode) as file:
        file.write(data)

    return {
        "path": path.relative_to(root.resolve()).as_posix(),
        "size": path.stat().st_size,
        "encoding": normalized_encoding,
        "appended": bool(append),
    }


def read_workspace_file(
    root: Path,
    *,
    relative_path: str,
    encoding: str = "utf-8",
    max_chars: int = 12000,
) -> dict[str, Any]:
    path = safe_workspace_path(root, relative_path)
    if not path.is_file():
        return {"error": f"file not found: {relative_path}"}

    max_chars = max(100, min(int(max_chars or 12000), 100000))
    data = path.read_bytes()
    normalized_encoding = str(encoding or "utf-8").lower()
    if normalized_encoding in {"utf-8", "utf8", "text"}:
        content = data.decode("utf-8", errors="replace")
    elif normalized_encoding == "base64":
        content = base64.b64encode(data).decode("ascii")
    else:
        return {"error": "encoding must be utf-8 or base64"}

    return {
        "path": path.relative_to(root.resolve()).as_posix(),
        "size": len(data),
        "encoding": normalized_encoding,
        "content": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


def list_workspace_files(root: Path, max_depth: int = 4) -> dict[str, Any]:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    max_depth = max(0, min(int(max_depth or 4), 10))
    entries: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        rel = path.relative_to(root)
        if len(rel.parts) > max_depth:
            continue
        entries.append(
            {
                "path": rel.as_posix(),
                "type": "dir" if path.is_dir() else "file",
                "size": path.stat().st_size if path.is_file() else None,
            }
        )
    entries.sort(key=lambda item: (item["type"] != "dir", item["path"]))
    return {"files": entries}


def normalize_command(command: Any) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command, posix=os.name != "nt")
    if isinstance(command, list):
        return [str(item) for item in command if str(item)]
    return []


def _normalized_executable_name(value: str) -> str:
    name = Path(str(value or "")).name.lower()
    return name[:-4] if name.endswith(".exe") else name


def run_workspace_command(
    root: Path,
    *,
    command: Any,
    cwd_relative: str | None = None,
    allowed_commands: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    cmd = normalize_command(command)
    if not cmd:
        return {"error": "empty command"}

    allowed = {
        _normalized_executable_name(item.strip())
        for item in str(allowed_commands or "").split(",")
        if item.strip()
    }
    executable = _normalized_executable_name(cmd[0])
    if allowed and executable not in allowed:
        return {
            "error": f"command not allowed: {cmd[0]}",
            "allowed_commands": sorted(allowed),
        }

    cwd = root.resolve()
    if cwd_relative:
        cwd = safe_workspace_path(root, cwd_relative, allow_root=True)
        if not cwd.is_dir():
            return {"error": f"cwd_relative is not a directory: {cwd_relative}"}

    temp_dir = root.resolve() / ".runtime-tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "AGENT_RUNTIME_WORKSPACE": str(root.resolve()),
            "HOME": str(root.resolve()),
            "TMP": str(temp_dir),
            "TEMP": str(temp_dir),
            "TMPDIR": str(temp_dir),
        }
    )

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=max(1, min(int(timeout or 60), 300)),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "error": f"command timed out after {exc.timeout} seconds",
            "command": cmd,
        }
    except Exception as exc:
        return {"error": str(exc), "command": cmd}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "command": cmd,
        "cwd": cwd.relative_to(root.resolve()).as_posix() or ".",
        "returncode": proc.returncode,
        "stdout": stdout[:MAX_COMMAND_OUTPUT_CHARS],
        "stderr": stderr[:MAX_COMMAND_OUTPUT_CHARS],
        "stdout_truncated": len(stdout) > MAX_COMMAND_OUTPUT_CHARS,
        "stderr_truncated": len(stderr) > MAX_COMMAND_OUTPUT_CHARS,
    }


def run_workspace_python(
    root: Path,
    *,
    code: str,
    script_name: str = "generated_script.py",
    timeout: int = 60,
) -> dict[str, Any]:
    script_path = str(script_name or "generated_script.py").replace("\\", "/")
    if not script_path.lower().endswith(".py"):
        script_path += ".py"
    if "/" not in script_path:
        script_path = f".runtime-scripts/{script_path}"

    write_result = write_workspace_file(
        root,
        relative_path=script_path,
        content=str(code or ""),
        encoding="utf-8",
        append=False,
        max_file_bytes=2 * 1024 * 1024,
    )
    result = run_workspace_command(
        root,
        command=[sys.executable, write_result["path"]],
        allowed_commands=_normalized_executable_name(sys.executable),
        timeout=timeout,
    )
    result["script_path"] = write_result["path"]
    return result


def prepare_workspace_export(
    root: Path,
    relative_path: str,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> WorkspaceExport:
    path = safe_workspace_path(root, relative_path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"file not found: {relative_path}")

    size = path.stat().st_size
    max_bytes = _bounded_file_limit(max_file_bytes)
    if size > max_bytes:
        raise RuntimeError(f"file exceeds export limit of {max_bytes} bytes")

    suffix = path.suffix.lower()
    mime_type = MIME_TYPE_OVERRIDES.get(suffix)
    if not mime_type:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return WorkspaceExport(
        relative_path=path.relative_to(root.resolve()).as_posix(),
        absolute_path=path,
        filename=path.name,
        mime_type=mime_type,
        size=size,
    )


def collect_exportable_files(
    root: Path,
    *,
    max_files: int = 10,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> list[WorkspaceExport]:
    root = root.resolve()
    exports: list[WorkspaceExport] = []
    if not root.is_dir():
        return exports

    for path in sorted(root.rglob("*")):
        if len(exports) >= max(1, min(int(max_files or 10), 25)):
            break
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if path.suffix.lower() not in EXPORTABLE_EXTENSIONS:
            continue
        try:
            exports.append(
                prepare_workspace_export(
                    root,
                    rel.as_posix(),
                    max_file_bytes=max_file_bytes,
                )
            )
        except RuntimeError:
            continue
    return exports
