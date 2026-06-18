from __future__ import annotations

import mimetypes
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from skills.package_store import (
    delete_skill,
    get_skill_zip,
    install_skill_files,
    list_installed_skills,
)


class SkillManagerTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        command = str(tool_parameters.get("command") or "").strip().lower()
        skill_name = str(tool_parameters.get("skill_name") or "").strip()
        overwrite = bool(tool_parameters.get("overwrite") or False)
        storage = self.session.storage

        if command in {"list", "查看", "查看技能"}:
            skills = list_installed_skills(storage)
            if not skills:
                yield self.create_text_message("No installed skill packages.")
                return
            lines = []
            for item in skills:
                name = item.get("name") or ""
                desc = item.get("description") or ""
                size = item.get("size") or 0
                lines.append(f"- {name} ({size} bytes): {desc}")
            yield self.create_text_message("\n".join(lines))
            return

        if command in {"install", "add", "新增", "新增技能", "安装", "安装技能"}:
            files_param = tool_parameters.get("files")
            if isinstance(files_param, list):
                file_items = [item for item in files_param if item]
            elif files_param:
                file_items = [files_param]
            else:
                file_items = []

            if not file_items:
                yield self.create_text_message("No zip files were provided.")
                return

            try:
                installed = install_skill_files(storage, file_items, overwrite=overwrite)
            except Exception as exc:
                yield self.create_text_message(f"Failed to install skill package: {exc}")
                return

            lines = ["Installed skill package(s):"]
            for item in installed:
                lines.append(f"- {item.get('name')}: {item.get('description') or ''}")
            yield self.create_text_message("\n".join(lines))
            return

        if command in {"delete", "remove", "删除", "删除技能"}:
            if not skill_name:
                yield self.create_text_message("skill_name is required for delete.")
                return
            if delete_skill(storage, skill_name):
                yield self.create_text_message(f"Deleted skill package: {skill_name}")
            else:
                yield self.create_text_message(f"Skill package not found: {skill_name}")
            return

        if command in {"download", "下载", "下载技能"}:
            if not skill_name:
                yield self.create_text_message("skill_name is required for download.")
                return
            payload = get_skill_zip(storage, skill_name)
            if not payload:
                yield self.create_text_message(f"Skill package not found: {skill_name}")
                return
            filename = f"{skill_name}.zip"
            mime_type, _ = mimetypes.guess_type(filename)
            yield self.create_blob_message(
                blob=payload,
                meta={
                    "mime_type": mime_type or "application/zip",
                    "filename": filename,
                },
            )
            return

        yield self.create_text_message("Unknown command. Use one of: install, list, delete, download.")
