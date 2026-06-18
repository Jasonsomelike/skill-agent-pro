"""
Persistent storage helpers for installable skill packages.

Installed skills are stored as individual zip archives in Dify plugin storage and
hydrated into a temporary directory for each strategy invocation. This keeps the
runtime independent from writable plugin package files.
"""

from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

import yaml


INDEX_KEY = "agent_skill_plugin.installed_skills.v1"
PACKAGE_KEY_PREFIX = "agent_skill_plugin.skill_package.v1."
SKILL_FILENAME = "SKILL.md"
MAX_TEXT_CHARS = 12000
MAX_COMMAND_OUTPUT_CHARS = 30000


def storage_get_text(storage: Any, key: str) -> str:
    try:
        val = storage.get(key)
    except Exception:
        return ""
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="ignore")
    if isinstance(val, str):
        return val
    return ""


def storage_set_text(storage: Any, key: str, text: str) -> None:
    storage.set(key, (text or "").encode("utf-8"))


def storage_get_json(storage: Any, key: str) -> dict[str, Any]:
    raw = storage_get_text(storage, key).strip()
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except Exception:
        return {}
    return val if isinstance(val, dict) else {}


def storage_set_json(storage: Any, key: str, value: dict[str, Any]) -> None:
    storage_set_text(storage, key, json.dumps(value, ensure_ascii=False))


def storage_get_bytes(storage: Any, key: str) -> bytes:
    try:
        val = storage.get(key)
    except Exception:
        return b""
    if val is None:
        return b""
    if isinstance(val, bytes):
        return val
    if isinstance(val, str):
        return val.encode("utf-8")
    return b""


def storage_set_bytes(storage: Any, key: str, data: bytes) -> None:
    storage.set(key, data or b"")


def package_key(skill_name: str) -> str:
    return PACKAGE_KEY_PREFIX + safe_storage_id(skill_name)


def safe_storage_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "skill"


def read_index(storage: Any) -> dict[str, Any]:
    index = storage_get_json(storage, INDEX_KEY)
    skills = index.get("skills")
    if not isinstance(skills, list):
        skills = []
    normalized = []
    for item in skills:
        if isinstance(item, dict) and item.get("name"):
            normalized.append(item)
    return {"skills": normalized}


def write_index(storage: Any, index: dict[str, Any]) -> None:
    skills = index.get("skills")
    if not isinstance(skills, list):
        skills = []
    skills.sort(key=lambda item: str(item.get("name", "")).lower())
    storage_set_json(storage, INDEX_KEY, {"skills": skills})


def list_installed_skills(storage: Any) -> list[dict[str, Any]]:
    return list(read_index(storage).get("skills") or [])


def extract_url_and_name(file_item: Any) -> tuple[str | None, str | None]:
    url = None
    name = None
    if hasattr(file_item, "url"):
        url = getattr(file_item, "url", None)
    if hasattr(file_item, "filename"):
        name = getattr(file_item, "filename", None)
    if hasattr(file_item, "name") and not name:
        name = getattr(file_item, "name", None)
    if isinstance(file_item, dict):
        url = file_item.get("url", url)
        name = file_item.get("filename", name) or file_item.get("name", name)
    return url, name


def download_file_content(url: str, timeout: int = 45) -> bytes:
    req = Request(url, headers={"User-Agent": "dify-agent-skill-plugin/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def infer_ext_from_url(url: str) -> str:
    ext = Path(urlparse(url).path).suffix
    return ext or ".zip"


def safe_filename(preferred_name: str | None, fallback_ext: str = ".zip") -> str:
    if preferred_name:
        name = Path(preferred_name).name
        name = re.sub(r"[<>:\"/\\|?*]+", "_", name).strip()
        if name:
            return name
    return f"{int(time.time())}{fallback_ext}"


def is_within_dir(base: Path, target: Path) -> bool:
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    return base_resolved == target_resolved or base_resolved in target_resolved.parents


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name:
                continue
            if name.startswith("/") or name.startswith("\\"):
                raise RuntimeError("zip contains an absolute path")
            target_path = (dest_dir / name).resolve()
            if not is_within_dir(dest_dir, target_path):
                raise RuntimeError("zip contains a path traversal entry")
            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


def parse_skill_markdown(skill_file: Path) -> tuple[dict[str, Any], str]:
    content = skill_file.read_text(encoding="utf-8")
    normalized = content.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized.strip()
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return {}, normalized.strip()
    frontmatter_raw = normalized[4:end]
    body = normalized[end + len("\n---\n") :].strip()
    try:
        frontmatter = yaml.safe_load(frontmatter_raw) or {}
    except yaml.YAMLError:
        frontmatter = {}
    return frontmatter if isinstance(frontmatter, dict) else {}, body


def find_skill_dirs(extracted_root: Path) -> list[Path]:
    if (extracted_root / SKILL_FILENAME).is_file():
        return [extracted_root]

    candidates: list[Path] = []
    for skill_file in extracted_root.rglob(SKILL_FILENAME):
        try:
            rel_depth = len(skill_file.parent.relative_to(extracted_root).parts)
        except ValueError:
            continue
        if rel_depth <= 3:
            candidates.append(skill_file.parent)

    unique: list[Path] = []
    seen = set()
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved not in seen:
            unique.append(candidate)
            seen.add(resolved)
    return unique


def skill_metadata_from_dir(skill_dir: Path) -> dict[str, Any]:
    skill_file = skill_dir / SKILL_FILENAME
    if not skill_file.is_file():
        raise RuntimeError(f"{skill_dir.name} does not contain {SKILL_FILENAME}")

    frontmatter, body = parse_skill_markdown(skill_file)
    config_file = skill_dir / "config.yaml"
    if config_file.is_file():
        try:
            config = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
            if isinstance(config, dict):
                frontmatter = {**frontmatter, **config}
        except yaml.YAMLError:
            pass

    name = str(frontmatter.get("name") or skill_dir.name).strip()
    if not name:
        name = skill_dir.name
    description = str(frontmatter.get("description") or "").strip()
    if not description:
        first_line = next((line.strip("# ").strip() for line in body.splitlines() if line.strip()), "")
        description = first_line[:200]

    triggers = frontmatter.get("triggers") or []
    if not isinstance(triggers, list):
        triggers = []

    return {
        "name": name,
        "folder": safe_storage_id(name),
        "description": description,
        "triggers": [str(item) for item in triggers],
    }


def make_skill_zip(skill_dir: Path, folder_name: str) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        for path in skill_dir.rglob("*"):
            if path.is_dir():
                continue
            arcname = Path(folder_name) / path.relative_to(skill_dir)
            zf.write(path, arcname.as_posix())
    return buf.getvalue()


def install_skill_archives(
    storage: Any,
    archive_payloads: list[tuple[str, bytes]],
    *,
    overwrite: bool = False,
) -> list[dict[str, Any]]:
    import tempfile

    index = read_index(storage)
    by_name = {str(item.get("name")): item for item in index.get("skills", [])}
    installed: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="skill-install-") as temp_root_raw:
        temp_root = Path(temp_root_raw)
        for filename, payload in archive_payloads:
            archive_path = temp_root / safe_filename(filename, infer_ext_from_url(filename))
            archive_path.write_bytes(payload)
            extract_root = temp_root / f"extract-{safe_storage_id(filename)}"
            safe_extract_zip(archive_path, extract_root)
            skill_dirs = find_skill_dirs(extract_root)
            if not skill_dirs:
                raise RuntimeError(f"{filename}: no skill folder containing {SKILL_FILENAME} found")

            for skill_dir in skill_dirs:
                meta = skill_metadata_from_dir(skill_dir)
                name = str(meta["name"])
                folder = str(meta["folder"])
                if name in by_name and not overwrite:
                    raise RuntimeError(f"skill already exists: {name}")
                zip_bytes = make_skill_zip(skill_dir, folder)
                storage_set_bytes(storage, package_key(name), zip_bytes)
                record = {
                    **meta,
                    "size": len(zip_bytes),
                    "installed_at": int(time.time()),
                }
                by_name[name] = record
                installed.append(record)

    write_index(storage, {"skills": list(by_name.values())})
    return installed


def install_skill_files(storage: Any, file_items: list[Any], *, overwrite: bool = False) -> list[dict[str, Any]]:
    payloads: list[tuple[str, bytes]] = []
    for item in file_items:
        url, preferred_name = extract_url_and_name(item)
        if not url:
            raise RuntimeError("uploaded file has no URL")
        filename = safe_filename(preferred_name, infer_ext_from_url(url))
        payloads.append((filename, download_file_content(str(url))))
    return install_skill_archives(storage, payloads, overwrite=overwrite)


def delete_skill(storage: Any, skill_name: str) -> bool:
    name = str(skill_name or "").strip()
    if not name:
        return False
    index = read_index(storage)
    skills = [item for item in index.get("skills", []) if item.get("name") != name]
    if len(skills) == len(index.get("skills", [])):
        return False
    storage_set_bytes(storage, package_key(name), b"")
    write_index(storage, {"skills": skills})
    return True


def get_skill_zip(storage: Any, skill_name: str) -> bytes:
    return storage_get_bytes(storage, package_key(skill_name))


def hydrate_installed_skills(storage: Any, dest_root: Path) -> dict[str, Path]:
    dest_root.mkdir(parents=True, exist_ok=True)
    hydrated: dict[str, Path] = {}
    for item in list_installed_skills(storage):
        name = str(item.get("name") or "").strip()
        folder = safe_storage_id(str(item.get("folder") or name))
        if not name:
            continue
        payload = get_skill_zip(storage, name)
        if not payload:
            continue
        zip_path = dest_root / f"{folder}.zip"
        zip_path.write_bytes(payload)
        safe_extract_zip(zip_path, dest_root)
        zip_path.unlink(missing_ok=True)
        skill_dir = dest_root / folder
        if skill_dir.is_dir():
            hydrated[name] = skill_dir
    return hydrated


def list_dir(root: Path, max_depth: int = 3) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    max_depth = max(0, min(max_depth, 10))
    root = root.resolve()
    for path in root.rglob("*"):
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
    return entries


def find_hydrated_skill_dir(skill_root: Path, skill_name: str) -> Path | None:
    wanted = str(skill_name or "").strip()
    if not wanted or not skill_root.is_dir():
        return None
    for child in skill_root.iterdir():
        if not child.is_dir() or not (child / SKILL_FILENAME).is_file():
            continue
        try:
            meta = skill_metadata_from_dir(child)
        except Exception:
            continue
        if meta.get("name") == wanted or child.name == wanted:
            return child
    return None


def safe_child_path(base: Path, relative_path: str) -> Path:
    rel = str(relative_path or "").replace("\\", "/").lstrip("/")
    target = (base / rel).resolve()
    if not is_within_dir(base, target):
        raise RuntimeError("path escapes skill directory")
    return target


def read_skill_file(skill_root: Path, skill_name: str, relative_path: str, max_chars: int = MAX_TEXT_CHARS) -> dict[str, Any]:
    skill_dir = find_hydrated_skill_dir(skill_root, skill_name)
    if not skill_dir:
        return {"error": f"skill not found: {skill_name}"}
    path = safe_child_path(skill_dir, relative_path)
    if not path.is_file():
        return {"error": f"file not found: {relative_path}"}
    text = path.read_text(encoding="utf-8", errors="replace")
    max_chars = max(100, min(int(max_chars or MAX_TEXT_CHARS), 100000))
    return {
        "skill_name": skill_name,
        "path": str(relative_path),
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def list_skill_files(skill_root: Path, skill_name: str, max_depth: int = 3) -> dict[str, Any]:
    skill_dir = find_hydrated_skill_dir(skill_root, skill_name)
    if not skill_dir:
        return {"error": f"skill not found: {skill_name}"}
    return {"skill_name": skill_name, "files": list_dir(skill_dir, max_depth)}


def get_skill_metadata(skill_root: Path, skill_name: str) -> dict[str, Any]:
    skill_dir = find_hydrated_skill_dir(skill_root, skill_name)
    if not skill_dir:
        return {"error": f"skill not found: {skill_name}"}
    meta = skill_metadata_from_dir(skill_dir)
    content = (skill_dir / SKILL_FILENAME).read_text(encoding="utf-8", errors="replace")
    return {**meta, "skill_md": content[:MAX_TEXT_CHARS], "truncated": len(content) > MAX_TEXT_CHARS}


def normalize_command(command: Any) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    if isinstance(command, list):
        return [str(item) for item in command if str(item)]
    return []


def run_skill_command(
    skill_root: Path,
    *,
    skill_name: str,
    command: Any,
    cwd_relative: str | None = None,
    allowed_commands: str = "",
    timeout: int = 60,
) -> dict[str, Any]:
    skill_dir = find_hydrated_skill_dir(skill_root, skill_name)
    if not skill_dir:
        return {"error": f"skill not found: {skill_name}"}

    cmd = normalize_command(command)
    if not cmd:
        return {"error": "empty command"}

    allowed = {item.strip() for item in allowed_commands.split(",") if item.strip()}
    executable = Path(cmd[0]).name
    if allowed and executable not in allowed and cmd[0] not in allowed:
        return {"error": f"command not allowed: {cmd[0]}", "allowed_commands": sorted(allowed)}

    cwd = skill_dir
    if cwd_relative:
        cwd = safe_child_path(skill_dir, cwd_relative)
        if not cwd.is_dir():
            return {"error": f"cwd_relative is not a directory: {cwd_relative}"}

    env = os.environ.copy()
    env["SKILL_DIR"] = str(skill_dir)
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
    except Exception as exc:
        return {"error": str(exc), "command": cmd}

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "command": cmd,
        "cwd": str(cwd),
        "returncode": proc.returncode,
        "stdout": stdout[:MAX_COMMAND_OUTPUT_CHARS],
        "stderr": stderr[:MAX_COMMAND_OUTPUT_CHARS],
        "stdout_truncated": len(stdout) > MAX_COMMAND_OUTPUT_CHARS,
        "stderr_truncated": len(stderr) > MAX_COMMAND_OUTPUT_CHARS,
    }
