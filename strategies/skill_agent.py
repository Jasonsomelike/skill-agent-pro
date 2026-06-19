"""
Skill-based Agent Strategy.

This strategy combines three capability sources:
1. Built-in skills from the plugin package.
2. User-installed skill packages stored in Dify plugin storage.
3. Dify tools selected in the Agent node.
"""

import ast
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from pydantic import BaseModel

from dify_plugin.entities.agent import AgentInvokeMessage
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessage,
    PromptMessageTool,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.entities.tool import ToolInvokeMessage, ToolParameter, ToolProviderType
from dify_plugin.interfaces.agent import AgentModelConfig, AgentStrategy, ToolEntity

from skills import SkillContext, SkillLoader, SkillRegistry
from skills.besti_document import generate_besti_docx
from skills.package_store import (
    get_skill_metadata,
    hydrate_installed_skills,
    install_skill_files,
    list_installed_skills,
    list_skill_files,
    read_skill_file,
    run_skill_command,
)
from skills.runtime_workspace import (
    WorkspaceExport,
    collect_exportable_files,
    list_workspace_files,
    prepare_workspace_export,
    read_workspace_file,
    run_workspace_command,
    run_workspace_python,
    safe_workspace_path,
    save_workspace_blob,
    write_workspace_file,
)


class SkillAgentParams(BaseModel):
    """Parameters for the skill-based agent strategy."""

    model: AgentModelConfig
    tools: Optional[List[ToolEntity]] = None
    query: str
    enabled_skills: str = "all"
    custom_skills: str = ""
    skill_packages: Optional[Any] = None
    external_skills_dir: str = "/opt/dify-agent-skills"
    debug_mode: bool = False
    max_active_skills: int = 3
    semantic_skill_matching: bool = True
    history_turns: int = 10
    allow_skill_commands: bool = False
    allowed_commands: str = "python,python3,node,npm,npx,bun,sh,bash"
    allow_runtime_execution: bool = False
    runtime_allowed_commands: str = "python,python3,node,npm,npx,bun,sh,bash"
    runtime_command_timeout: int = 60
    runtime_max_file_mb: int = 20
    auto_export_files: bool = True
    maximum_iterations: int = 10


SkillAgentParams.model_rebuild(
    force=True,
    _types_namespace={
        "AgentModelConfig": AgentModelConfig,
        "ToolEntity": ToolEntity,
        "Any": Any,
        "List": List,
        "Optional": Optional,
    },
)


class SkillAgentAgentStrategy(AgentStrategy):
    """
    Agent strategy that uses installable skills and Dify tools.
    """

    BASE_SYSTEM_PROMPT = """You are an intelligent assistant with specialized skills.

Relevant skills may be activated based on the user's query. Follow the active
skill instructions while maintaining a helpful, professional tone.

When using tools:
1. Analyze the task and determine which tools are needed.
2. Call tools with appropriate parameters.
3. Use tool results to continue the task, not as the final answer by default.
4. If a tool fails, explain the issue and try a reasonable alternative.

When a knowledge-base tool returns source metadata or page images:
1. Preserve the exact document_name in the final answer. Do not shorten a
   split filename to a generic book title.
2. Read the page number from Markdown labels such as "Page 18" or URLs such
   as "page_18.jpg".
3. For filenames ending in "_partN_pA-B.pdf", report both the split-file page
   N and the original PDF page A + N - 1. Do not call that calculated PDF page
   the printed textbook page.
4. Copy returned /page-images/ URLs exactly into standard Markdown image
   syntax. Do not omit the image, output only a bare URL, or replace it with
   an illustration from inside the page.

When presenting a learning roadmap or "后续路线":
1. Use a fenced ```mermaid block with `flowchart LR` or `flowchart TD`.
2. Use simple ASCII node IDs and quoted Chinese labels.
3. Never use plain-text arrows, box-drawing characters, or an unlabeled code block.

When image-generation and Bilibili tools are available:
1. Use text2image only when the user requests an image or a visual materially
   improves understanding. Label generated images as AI teaching illustrations.
2. Use bilibili_search for learning-video discovery and
   bilibili_get_video_info to verify final recommendations.
3. Do not invent video metadata, timestamps, popularity, or content.

Installed skill packages may include reference files and scripts. Use the
skill_* tools to inspect those packages only when the active skill instructions
or the user task require deeper package content.

The runtime_* tools operate only inside a temporary workspace created for this
agent invocation. Put user deliverables in that workspace. For document,
spreadsheet, presentation, PDF, archive, image, or other file-generation tasks,
create the real file and call runtime_export_file so Dify returns it as an
attachment. Do not merely print source code when the requested file can be
generated in the workspace.

When long-term memory tools are available:
1. Use the runtime-bound user_id. Do not ask the user to repeat it.
2. Read memory before answering explicit questions about what was saved,
   remembered, updated, or missing.
3. Only say something was saved or updated after the tool result confirms it.
"""

    INTERNAL_TOOL_NAMES = {
        "skill_list_installed",
        "skill_get_metadata",
        "skill_list_files",
        "skill_read_file",
        "skill_run_command",
        "runtime_list_files",
        "runtime_read_file",
        "runtime_write_file",
        "runtime_run_python",
        "runtime_run_command",
        "runtime_export_file",
        "runtime_generate_besti_docx",
    }

    INTERNAL_TOOL_SCHEMAS: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "skill_list_installed",
                "description": "List installed skill packages available to this agent.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill_get_metadata",
                "description": "Read an installed skill package's SKILL.md and metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {"skill_name": {"type": "string"}},
                    "required": ["skill_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill_list_files",
                "description": "List files in an installed skill package.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "max_depth": {"type": "integer", "default": 3},
                    },
                    "required": ["skill_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill_read_file",
                "description": "Read a text file from an installed skill package.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "relative_path": {"type": "string"},
                        "max_chars": {"type": "integer", "default": 12000},
                    },
                    "required": ["skill_name", "relative_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "skill_run_command",
                "description": (
                    "Run a whitelisted command inside an installed skill package. "
                    "This is disabled unless Allow Skill Commands is enabled."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "command": {"type": "array", "items": {"type": "string"}},
                        "cwd_relative": {"type": "string"},
                    },
                    "required": ["skill_name", "command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_list_files",
                "description": "List files created in this invocation's temporary runtime workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_depth": {"type": "integer", "default": 4},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_read_file",
                "description": "Read a text or base64-encoded file from the runtime workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "relative_path": {"type": "string"},
                        "encoding": {
                            "type": "string",
                            "enum": ["utf-8", "base64"],
                            "default": "utf-8",
                        },
                        "max_chars": {"type": "integer", "default": 12000},
                    },
                    "required": ["relative_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_write_file",
                "description": (
                    "Write UTF-8 text or base64 bytes to a relative path in the runtime workspace."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "relative_path": {"type": "string"},
                        "content": {"type": "string"},
                        "encoding": {
                            "type": "string",
                            "enum": ["utf-8", "base64"],
                            "default": "utf-8",
                        },
                        "append": {"type": "boolean", "default": False},
                    },
                    "required": ["relative_path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_run_python",
                "description": (
                    "Execute Python code in the temporary runtime workspace. "
                    "Use installed libraries such as python-docx, openpyxl, python-pptx, "
                    "and reportlab to create real deliverable files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "script_name": {
                            "type": "string",
                            "default": "generated_script.py",
                        },
                        "timeout": {"type": "integer", "default": 60},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_run_command",
                "description": (
                    "Run an allowlisted command in the temporary runtime workspace. "
                    "Commands are executed without a shell."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "array", "items": {"type": "string"}},
                        "cwd_relative": {"type": "string"},
                        "timeout": {"type": "integer", "default": 60},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_export_file",
                "description": (
                    "Return a workspace file to the Dify user as a real downloadable attachment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"relative_path": {"type": "string"}},
                    "required": ["relative_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "runtime_generate_besti_docx",
                "description": (
                    "Generate a real Word DOCX using the Besti official-document standard: "
                    "A4; margins 3.6/3.0/2.7/2.7 cm; title in 22 pt Founder Small "
                    "Standard Song; body in 16 pt FangSong; exact 29 pt line spacing; "
                    "Chinese heading fonts; full-width list punctuation; centered page numbers. "
                    "Use this for every Word/DOCX request unless the user explicitly requests "
                    "another format. It can insert workspace images and structured tables."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "Output .docx filename."},
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "recipient": {"type": "string"},
                        "body": {
                            "type": "string",
                            "description": (
                                "Document body. Put each paragraph on its own line. "
                                "Use 一、, （一）, and 1． prefixes for heading levels."
                            ),
                        },
                        "organization": {"type": "string"},
                        "date_text": {"type": "string", "description": "Example: 2026 年 6 月 18 日"},
                        "document_type": {
                            "type": "string",
                            "enum": ["white-paper", "red-header", "meeting-minutes", "general"],
                            "default": "white-paper",
                        },
                        "header_text": {"type": "string"},
                        "document_number": {"type": "string"},
                        "attachments": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "images": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "path": {
                                        "type": "string",
                                        "description": "Relative path of an image in the runtime workspace.",
                                    },
                                    "caption": {"type": "string"},
                                    "width_cm": {"type": "number", "default": 14.0},
                                    "placement": {
                                        "type": "string",
                                        "enum": ["body", "attachment"],
                                        "default": "attachment",
                                    },
                                },
                                "required": ["path"],
                            },
                        },
                        "tables": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "headers": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "rows": {
                                        "type": "array",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "column_widths_cm": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                    },
                                    "placement": {
                                        "type": "string",
                                        "enum": ["body", "attachment"],
                                        "default": "attachment",
                                    },
                                },
                                "required": ["headers", "rows"],
                            },
                        },
                    },
                    "required": ["filename", "title", "body"],
                },
            },
        },
    ]

    def _parse_enabled_skills(self, enabled_skills: str) -> Optional[List[str]]:
        if not enabled_skills or enabled_skills.lower().strip() == "all":
            return None
        return [item.strip() for item in enabled_skills.split(",") if item.strip()]

    def _normalize_file_items(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return [item for item in value if item]
        if value:
            return [value]
        return []

    def _safe_get(self, value: Any, *path: str, default: Any = None) -> Any:
        current = value
        for key in path:
            if current is None:
                return default
            if isinstance(current, dict):
                current = current.get(key)
            else:
                current = getattr(current, key, None)
        return default if current is None else current

    def _to_llm_model_config(self, model: Any) -> LLMModelConfig:
        if isinstance(model, LLMModelConfig):
            payload = model.model_dump(mode="json")
        elif hasattr(model, "model_dump"):
            payload = model.model_dump(mode="json")
        elif isinstance(model, dict):
            payload = model
        else:
            raise TypeError(f"Unsupported model config type: {type(model).__name__}")
        return LLMModelConfig(**payload)

    def _tool_identity_name(self, tool: Any) -> str:
        return str(self._safe_get(tool, "identity", "name", default="") or "")

    def _tool_identity_provider(self, tool: Any) -> str:
        return str(self._safe_get(tool, "identity", "provider", default="") or "")

    def _tool_description_llm(self, tool: Any) -> str:
        return str(self._safe_get(tool, "description", "llm", default="") or "")

    def _tool_parameters(self, tool: Any) -> Any:
        return self._safe_get(tool, "parameters", default=[])

    def _tool_runtime_parameters(self, tool: Any) -> dict[str, Any]:
        params = self._safe_get(tool, "runtime_parameters", default={})
        return params if isinstance(params, dict) else {}

    def _tool_provider_type(self, tool: Any) -> Any:
        return self._safe_get(tool, "provider_type", default=ToolProviderType.BUILT_IN)

    def _is_allowed_external_skills_dir(self, path: Path) -> bool:
        allowed_roots = [
            Path("/opt/dify-agent-skills").resolve(),
            Path("/app/external-skills").resolve(),
        ]

        try:
            resolved = path.resolve()
        except Exception:
            return False

        return any(resolved == root or root in resolved.parents for root in allowed_roots)

    def _load_registry(
        self,
        storage: Any,
        installed_root: Path,
        external_skills_dir: str = "/opt/dify-agent-skills",
    ) -> tuple[SkillRegistry, int, int, int, dict[str, str]]:
        registry = SkillRegistry()
        skill_sources: dict[str, str] = {}

        def load_directory(directory: str | Path, source: str) -> None:
            loader = SkillLoader(str(directory))
            for skill in loader.load_all_skills():
                registry.register(skill)
                skill_sources[skill.config.name] = source

        current_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_dir = os.path.dirname(current_dir)

        # 1. Load built-in skills from the plugin package.
        builtin_skills_dir = os.path.join(plugin_dir, "skills")
        load_directory(builtin_skills_dir, "built-in")

        # 2. Load external server-side skills from an explicitly mounted directory.
        external_dir = str(external_skills_dir or "").strip()
        if external_dir:
            external_path = Path(external_dir).expanduser()
            if (
                self._is_allowed_external_skills_dir(external_path)
                and external_path.exists()
                and external_path.is_dir()
            ):
                load_directory(external_path, "external")

        # 3. Load zip-installed skills from plugin storage.
        hydrated = hydrate_installed_skills(storage, installed_root)
        if hydrated:
            load_directory(installed_root, "installed")

        builtin_count = sum(source == "built-in" for source in skill_sources.values())
        external_count = sum(source == "external" for source in skill_sources.values())
        installed_count = sum(source == "installed" for source in skill_sources.values())

        return registry, builtin_count, external_count, installed_count, skill_sources

    def _skill_inventory(
        self,
        registry: SkillRegistry,
        skill_sources: dict[str, str],
        skill_filter: Optional[List[str]] = None,
    ) -> list[dict[str, Any]]:
        inventory = []
        for skill in registry.list_skills():
            if skill_filter and skill.config.name not in skill_filter:
                continue
            inventory.append(
                {
                    "name": skill.config.name,
                    "description": skill.config.description,
                    "category": skill.config.category or "",
                    "triggers": list(skill.config.triggers),
                    "priority": skill.config.priority,
                    "source": skill_sources.get(skill.config.name, "custom"),
                }
            )
        return inventory

    def _format_selected_skills(
        self,
        registry: SkillRegistry,
        query: str,
        names: list[str],
    ) -> tuple[str, list[str]]:
        prompts = []
        selected_names = []
        for name in names:
            skill = registry.get(name)
            if skill is None or name in selected_names:
                continue
            ctx = SkillContext(
                query=query,
                matched_triggers=skill.get_matched_triggers(query),
            )
            prompts.append(skill.format_for_llm(ctx))
            selected_names.append(name)

        if not prompts:
            return "", []

        header = f"# Active Skills ({len(selected_names)})\n\n"
        header += "The following skills are relevant to this query:\n"
        header += "".join(f"- {name}\n" for name in selected_names)
        header += "\n---\n\n"
        return header + "\n\n---\n\n".join(prompts), selected_names

    def _message_text(self, message: Any) -> str:
        content = self._safe_get(message, "content", default=message)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                text = self._message_content_text(item)
                if text:
                    parts.append(text)
            return "\n".join(parts)
        if isinstance(content, dict):
            text = self._message_content_text(content)
            if text:
                return text
        return str(content or "")

    def _truncate_text(self, value: Any, limit: int = 180) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: max(1, limit - 1)] + "…"

    def _message_attachment_text(
        self,
        content_type: str,
        *,
        filename: str = "",
        mime_type: str = "",
        url: str = "",
    ) -> str:
        label = str(content_type or "content").strip().lower()
        details = []
        if filename:
            details.append(filename)
        elif mime_type:
            details.append(mime_type)

        normalized_url = str(url or "").strip()
        if normalized_url and not normalized_url.startswith("data:"):
            details.append(self._truncate_text(normalized_url, limit=120))

        if details:
            return f"[{label}: {' | '.join(details)}]"
        return f"[{label}]"

    def _message_content_text(self, item: Any) -> str:
        if item is None:
            return ""
        if isinstance(item, str):
            return item

        content_type = self._safe_get(item, "type", default="")
        content_type = str(getattr(content_type, "value", content_type) or "").lower()

        text = self._safe_get(item, "data", default=None)
        if text is None:
            text = self._safe_get(item, "text", default=None)
        if text and content_type in {"", "text"}:
            return str(text)

        if isinstance(item, dict) and not content_type:
            raw_content = item.get("content")
            if isinstance(raw_content, str):
                return raw_content

        filename = str(self._safe_get(item, "filename", default="") or "").strip()
        mime_type = str(self._safe_get(item, "mime_type", default="") or "").strip()
        url = str(self._safe_get(item, "url", default="") or "").strip()
        if url.startswith("data:"):
            url = ""

        if text and not content_type:
            return str(text)

        label = content_type
        if not label:
            label = item.__class__.__name__
            for suffix in ("PromptMessageContent", "MessageContent", "Content"):
                if label.endswith(suffix):
                    label = label[: -len(suffix)]
                    break
            label = label or "content"

        return self._message_attachment_text(
            label,
            filename=filename,
            mime_type=mime_type,
            url=url,
        )

    def _extract_primary_query(self, query: Any) -> str:
        text = str(query or "").strip()
        if not text:
            return ""

        marker = "用户请求："
        if marker not in text:
            return text

        remainder = text.split(marker, 1)[1].strip()
        delimiters = [
            "\n\n用户 ID：",
            "\n用户 ID：",
            "\n\n图片解析（没有图片时为空）：",
            "\n图片解析（没有图片时为空）：",
            "\n\n图片解析：",
            "\n图片解析：",
        ]
        end_index = len(remainder)
        for delimiter in delimiters:
            index = remainder.find(delimiter)
            if index >= 0:
                end_index = min(end_index, index)

        extracted = remainder[:end_index].strip()
        return extracted or text

    def _normalize_history_message(self, message: Any) -> PromptMessage | None:
        content = self._message_text(message)
        if isinstance(message, UserPromptMessage):
            return UserPromptMessage(content=content, name=message.name)
        if isinstance(message, AssistantPromptMessage):
            # Conversation history represents completed answers. Remove old tool
            # call metadata so it cannot create dangling tool-call sequences.
            return AssistantPromptMessage(content=content, name=message.name, tool_calls=[])

        if isinstance(message, dict):
            role_value = message.get("role")
            role = str(getattr(role_value, "value", role_value) or "").lower()
            name = message.get("name")
        else:
            role_value = getattr(message, "role", None)
            role = str(getattr(role_value, "value", role_value) or "").lower()
            name = getattr(message, "name", None)

        if role == "user":
            return UserPromptMessage(content=content, name=name)
        if role == "assistant":
            return AssistantPromptMessage(content=content, name=name, tool_calls=[])
        return None

    def _prepare_history_messages(
        self,
        model: Any,
        query: str,
        max_turns: int,
    ) -> tuple[list[PromptMessage], int]:
        if max_turns <= 0:
            return [], 0

        raw_history = self._safe_get(model, "history_prompt_messages", default=[]) or []
        if not isinstance(raw_history, list):
            return [], 0

        history = []
        current_query = str(query or "").strip()
        primary_query = self._extract_primary_query(current_query)
        for raw_message in raw_history:
            message = self._normalize_history_message(raw_message)
            if message is not None:
                history.append(message)

        # Some Dify versions may include the current query at the end of history.
        # Avoid sending it twice.
        if history and isinstance(history[-1], UserPromptMessage):
            last_text = self._message_text(history[-1]).strip()
            if last_text and last_text in {current_query, primary_query}:
                history.pop()

        user_positions = [
            index for index, message in enumerate(history) if isinstance(message, UserPromptMessage)
        ]
        if len(user_positions) > max_turns:
            history = history[user_positions[-max_turns] :]

        turn_count = sum(isinstance(message, UserPromptMessage) for message in history)
        return history, turn_count

    def _build_routing_context(
        self,
        history_messages: list[PromptMessage],
        query: str,
        max_chars: int = 6000,
    ) -> str:
        lines = []
        for message in history_messages:
            if isinstance(message, UserPromptMessage):
                role = "User"
            elif isinstance(message, AssistantPromptMessage):
                role = "Assistant"
            else:
                continue
            text = self._message_text(message).strip()
            if text:
                lines.append(f"{role}: {text[:1500]}")

        history_text = "\n".join(lines)
        if len(history_text) > max_chars:
            history_text = history_text[-max_chars:]
        if not history_text:
            return str(query or "")
        return (
            "Use the recent conversation to resolve references and follow-up requests.\n\n"
            f"Recent conversation:\n{history_text}\n\n"
            f"Current user request:\n{query}"
        )

    def _semantic_match_skills(
        self,
        model_config: LLMModelConfig,
        routing_context: str,
        inventory: list[dict[str, Any]],
        max_skills: int,
    ) -> list[dict[str, Any]]:
        if not inventory:
            return []

        router_prompt = (
            "You are a strict skill router. Select only skills that are semantically relevant "
            "to the user's request. A skill can be relevant even when none of its literal triggers "
            "appear in the query. Return JSON only in this format: "
            '{"skills":[{"name":"exact-skill-name","confidence":0.0,"reason":"short reason"}]}. '
            f"Select at most {max_skills} skills. Use an empty list when no skill is relevant. "
            "Do not invent names. Prefer precision over selecting a weakly related skill.\n\n"
            "Available skills:\n"
            + json.dumps(inventory, ensure_ascii=False)
        )
        response = self.session.model.llm.invoke(
            model_config=model_config,
            prompt_messages=[
                SystemPromptMessage(content=router_prompt),
                UserPromptMessage(content=routing_context),
            ],
            tools=None,
            stop=model_config.completion_params.get("stop", [])
            if getattr(model_config, "completion_params", None)
            else [],
            stream=False,
        )

        if hasattr(response, "message"):
            text = self._message_text(response.message)
        else:
            text_parts = []
            for chunk in response:
                delta = self._safe_get(chunk, "delta", default=None)
                message = self._safe_get(delta, "message", default=delta or chunk)
                text_parts.append(self._message_text(message))
            text = "".join(text_parts)

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except Exception:
            return []

        raw_matches = payload.get("skills") if isinstance(payload, dict) else None
        if not isinstance(raw_matches, list):
            return []

        allowed_names = {item["name"] for item in inventory}
        matches = []
        for item in raw_matches:
            if isinstance(item, str):
                name = item
                confidence = 0.75
                reason = ""
            elif isinstance(item, dict):
                name = str(item.get("name") or "")
                try:
                    confidence = float(item.get("confidence", 0))
                except (TypeError, ValueError):
                    confidence = 0.0
                reason = str(item.get("reason") or "")
            else:
                continue
            if name in allowed_names and confidence >= 0.55:
                matches.append(
                    {
                        "name": name,
                        "confidence": min(max(confidence, 0.0), 1.0),
                        "reason": reason,
                    }
                )
            if len(matches) >= max_skills:
                break
        return matches

    def _tool_parameter_type_to_json_schema_type(self, parameter_type: Any) -> str:
        """Map Dify ToolParameter types to JSON Schema primitive types."""
        raw = getattr(parameter_type, "value", parameter_type)
        raw = str(raw or "string").lower()
        if raw in {"number", "integer"}:
            return raw
        if raw in {"boolean", "bool"}:
            return "boolean"
        if raw in {"array", "object"}:
            return raw
        # select/secret-input/text-input/string/file-like values are represented as strings for LLM tool calls.
        return "string"

    def _option_value(self, option: Any) -> Any:
        if isinstance(option, dict):
            return option.get("value") or option.get("label")
        return getattr(option, "value", None) or getattr(option, "label", None) or str(option)

    def _schema_to_prompt_message_tool(self, schema: dict[str, Any]) -> PromptMessageTool:
        function = schema.get("function") or {}
        return PromptMessageTool(
            name=str(function.get("name") or ""),
            description=str(function.get("description") or ""),
            parameters=function.get("parameters")
            or {"type": "object", "properties": {}, "required": []},
        )

    def _convert_tool_to_prompt_message_tool(self, tool: Any) -> PromptMessageTool:
        """Convert a Dify ToolEntity or a dict-like tool definition to PromptMessageTool."""
        tool_name = self._tool_identity_name(tool)
        description = self._tool_description_llm(tool)
        parameters = self._tool_parameters(tool)

        # Some SDK/runtime versions may already provide a JSON-schema parameters dict.
        if isinstance(parameters, dict) and parameters.get("type") == "object":
            return PromptMessageTool(
                name=tool_name,
                description=description,
                parameters=parameters,
            )

        message_tool = PromptMessageTool(
            name=tool_name,
            description=description,
            parameters={"type": "object", "properties": {}, "required": []},
        )

        # Official Dify ToolEntity.parameters is a list[ToolParameter].
        for parameter in parameters or []:
            form = self._safe_get(parameter, "form")
            if form not in {ToolParameter.ToolParameterForm.LLM, "llm"}:
                continue

            parameter_type = self._safe_get(parameter, "type")
            if parameter_type in {
                ToolParameter.ToolParameterType.FILE,
                ToolParameter.ToolParameterType.FILES,
                "file",
                "files",
            }:
                continue

            name = str(self._safe_get(parameter, "name", default="") or "")
            if not name:
                continue

            field_schema: dict[str, Any] = {
                "type": self._tool_parameter_type_to_json_schema_type(parameter_type),
                "description": str(
                    self._safe_get(parameter, "llm_description", default="")
                    or self._safe_get(parameter, "human_description", default="")
                    or ""
                ),
            }

            raw_type = str(getattr(parameter_type, "value", parameter_type) or "").lower()
            if raw_type == "select":
                options = self._safe_get(parameter, "options", default=[]) or []
                enum_values = [self._option_value(option) for option in options]
                enum_values = [value for value in enum_values if value not in {None, ""}]
                if enum_values:
                    field_schema["enum"] = enum_values

            message_tool.parameters["properties"][name] = field_schema
            if bool(self._safe_get(parameter, "required", default=False)):
                message_tool.parameters["required"].append(name)

        return message_tool

    def _build_tool_definitions(
        self,
        tools: Optional[List[ToolEntity]],
        *,
        include_skill_commands: bool,
        include_runtime_execution: bool,
    ) -> List[PromptMessageTool]:
        definitions: list[PromptMessageTool] = []

        for schema in self.INTERNAL_TOOL_SCHEMAS:
            name = schema["function"]["name"]
            if name == "skill_run_command" and not include_skill_commands:
                continue
            if name in {"runtime_run_python", "runtime_run_command"} and not include_runtime_execution:
                continue
            definitions.append(self._schema_to_prompt_message_tool(schema))

        for tool in tools or []:
            tool_name = self._tool_identity_name(tool)
            if not tool_name:
                continue
            definitions.append(self._convert_tool_to_prompt_message_tool(tool))

        return definitions

    def _parse_tool_arguments(self, raw_args: Any) -> dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            if not raw_args.strip():
                return {}
            try:
                parsed = json.loads(raw_args)
            except Exception:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _extract_tool_calls(self, message: Any) -> List[Tuple[str, str, Dict[str, Any]]]:
        tool_calls = []
        raw_calls = None

        if hasattr(message, "tool_calls"):
            raw_calls = getattr(message, "tool_calls", None)
        elif isinstance(message, dict):
            raw_calls = message.get("tool_calls")

        if not raw_calls:
            return []

        for index, call in enumerate(raw_calls):
            call_id = getattr(call, "id", None)
            function = getattr(call, "function", None)
            name = getattr(function, "name", None) if function is not None else None
            args = getattr(function, "arguments", None) if function is not None else None

            if isinstance(call, dict):
                call_id = call.get("id", call_id)
                function_dict = call.get("function") or {}
                if isinstance(function_dict, dict):
                    name = function_dict.get("name", name)
                    args = function_dict.get("arguments", args)

            if not name:
                continue
            tool_calls.append((str(call_id or f"call_{index}"), str(name), self._parse_tool_arguments(args)))

        return tool_calls

    def _assistant_tool_call_objects(self, tool_calls: list[tuple[str, str, dict[str, Any]]]) -> Any:
        try:
            return [
                AssistantPromptMessage.ToolCall(
                    id=call_id,
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name=name,
                        arguments=json.dumps(args, ensure_ascii=False),
                    ),
                )
                for call_id, name, args in tool_calls
            ]
        except Exception:
            return tool_calls

    def _stringify_tool_message(self, result: ToolInvokeMessage) -> str:
        message = getattr(result, "message", None)
        if message is None:
            return ""
        if hasattr(message, "text"):
            return str(getattr(message, "text") or "")
        if hasattr(message, "json_object"):
            try:
                return json.dumps(getattr(message, "json_object"), ensure_ascii=False)
            except Exception:
                return str(getattr(message, "json_object"))
        if hasattr(message, "blob"):
            return "Tool returned a file/blob."
        return str(message)

    def _split_document_page(
        self,
        document_name: str,
        local_page: int,
    ) -> tuple[Optional[int], Optional[int], Optional[int]]:
        match = re.search(
            r"_part\d+_p(?P<start>\d+)-(?P<end>\d+)\.pdf$",
            document_name,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None, None, None

        start_page = int(match.group("start"))
        end_page = int(match.group("end"))
        original_pdf_page = start_page + local_page - 1
        if original_pdf_page > end_page:
            return start_page, end_page, None
        return start_page, end_page, original_pdf_page

    def _extract_knowledge_citations(self, tool_result: str) -> list[dict[str, Any]]:
        if not tool_result:
            return []

        citations: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for record in self._knowledge_result_records(tool_result):
            document_name = self._find_nested_string(record, "document_name")
            content = self._find_nested_string(record, "content")
            if not content:
                continue

            image_matches = re.finditer(
                r"""!\[(?P<label>[^\]]*)\]\((?P<url>https?://[^)\s]+/page_(?P<url_page>\d+)\.(?:jpg|jpeg|png|webp))\)""",
                content,
                flags=re.IGNORECASE,
            )
            for image_match in image_matches:
                url = image_match.group("url")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                label_match = re.search(
                    r"\bPage\s*(\d+)\b",
                    image_match.group("label"),
                    flags=re.IGNORECASE,
                )
                local_page = (
                    int(label_match.group(1))
                    if label_match
                    else int(image_match.group("url_page"))
                )
                start_page, end_page, original_pdf_page = self._split_document_page(
                    document_name,
                    local_page,
                )
                citations.append(
                    {
                        "document_name": document_name,
                        "local_page": local_page,
                        "original_pdf_page": original_pdf_page,
                        "split_start_page": start_page,
                        "split_end_page": end_page,
                        "image_url": url,
                    }
                )
        return citations

    def _knowledge_result_records(self, tool_result: str) -> list[dict[str, Any]]:
        candidates: list[Any] = []
        stripped = tool_result.strip()

        try:
            candidates.append(json.loads(stripped))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

        marker = "variable_value="
        if marker in stripped:
            literal_text = stripped.split(marker, 1)[1].strip()
            try:
                candidates.append(ast.literal_eval(literal_text))
            except (SyntaxError, ValueError):
                pass

        records: list[dict[str, Any]] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                if self._find_nested_string(value, "content") and self._find_nested_string(
                    value,
                    "document_name",
                ):
                    records.append(value)
                    return
                for nested in value.values():
                    collect(nested)
            elif isinstance(value, list):
                for nested in value:
                    collect(nested)
            elif isinstance(value, str) and marker in value:
                nested_literal = value.split(marker, 1)[1].strip()
                try:
                    collect(ast.literal_eval(nested_literal))
                except (SyntaxError, ValueError):
                    return

        for candidate in candidates:
            collect(candidate)

        if records:
            return records

        # Conservative fallback for unusual wrappers: only pair an image with a
        # document_name when both occur inside the same dictionary-like block.
        for block_match in re.finditer(
            r"\{[^{}]*?['\"]content['\"]\s*:\s*(?P<content>.+?)"
            r"['\"]document_name['\"]\s*:\s*['\"](?P<document>[^'\"]+)['\"][^{}]*?\}",
            stripped,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            records.append(
                {
                    "content": block_match.group("content"),
                    "document_name": block_match.group("document"),
                }
            )
        return records

    def _find_nested_string(self, value: Any, target_key: str) -> str:
        if isinstance(value, dict):
            direct = value.get(target_key)
            if isinstance(direct, str) and direct.strip():
                return direct.strip()
            for nested in value.values():
                found = self._find_nested_string(nested, target_key)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = self._find_nested_string(nested, target_key)
                if found:
                    return found
        return ""

    def _merge_knowledge_citations(
        self,
        existing: list[dict[str, Any]],
        incoming: list[dict[str, Any]],
    ) -> None:
        known_urls = {str(item.get("image_url") or "") for item in existing}
        for citation in incoming:
            url = str(citation.get("image_url") or "")
            if not url or url in known_urls:
                continue
            existing.append(citation)
            known_urls.add(url)

    def _knowledge_citation_hint(self, citations: list[dict[str, Any]]) -> str:
        if not citations:
            return ""

        lines = [
            "",
            "[Knowledge citation normalization]",
            "The final answer must preserve these exact source files and page images:",
        ]
        for citation in citations:
            document_name = str(citation.get("document_name") or "document_name 未提供")
            local_page = int(citation["local_page"])
            original_pdf_page = citation.get("original_pdf_page")
            if original_pdf_page is None:
                page_text = f"第 {local_page} 页"
            else:
                page_text = f"原 PDF 第 {original_pdf_page} 页（分卷内第 {local_page} 页）"
            lines.append(
                f"- 文件：{document_name}；页码：{page_text}；"
                f"整页图片：{citation['image_url']}"
            )
        return "\n".join(lines)

    def _missing_knowledge_citation_appendix(
        self,
        response_text: str,
        citations: list[dict[str, Any]],
        max_images: int = 3,
    ) -> str:
        if not citations:
            return ""

        blocks = []
        for citation in citations[: max(1, max_images)]:
            document_name = str(citation.get("document_name") or "document_name 未提供")
            image_url = str(citation.get("image_url") or "")
            local_page = int(citation["local_page"])
            original_pdf_page = citation.get("original_pdf_page")

            has_exact_document = document_name in response_text
            has_image = image_url in response_text
            if has_exact_document and has_image:
                continue

            lines = [f"来源文件：`{document_name}`"]
            if original_pdf_page is None:
                lines.append(f"来源页码：第 {local_page} 页")
                image_page_label = f"第 {local_page} 页"
            else:
                lines.append(
                    f"来源页码：原 PDF 第 {original_pdf_page} 页"
                    f"（分卷内第 {local_page} 页）"
                )
                image_page_label = (
                    f"原 PDF 第 {original_pdf_page} 页，分卷内第 {local_page} 页"
                )

            if not has_image:
                lines.append(
                    f"![{document_name} {image_page_label}原页]({image_url})"
                )
            blocks.append("\n".join(lines))

        if not blocks:
            return ""
        return "\n\n## 知识库来源原页\n\n" + "\n\n".join(blocks)

    def _execute_internal_tool(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any],
        storage: Any,
        installed_root: Path,
        workspace_root: Path,
        params: SkillAgentParams,
        registry: SkillRegistry,
        skill_sources: dict[str, str],
    ) -> tuple[dict[str, Any], list[WorkspaceExport]]:
        max_file_bytes = max(
            1,
            min(int(params.runtime_max_file_mb or 20), 100),
        ) * 1024 * 1024

        if tool_name == "skill_list_installed":
            return {"skills": self._skill_inventory(registry, skill_sources)}, []

        if tool_name == "runtime_generate_besti_docx":
            filename = str(tool_args.get("filename") or "Besti公文.docx").strip()
            if not filename.lower().endswith(".docx"):
                filename += ".docx"
            output_path = safe_workspace_path(workspace_root, filename)
            result = generate_besti_docx(
                workspace_root,
                output_path=output_path,
                title=str(tool_args.get("title") or "公文"),
                subtitle=str(tool_args.get("subtitle") or ""),
                recipient=str(tool_args.get("recipient") or ""),
                body=str(tool_args.get("body") or ""),
                organization=str(tool_args.get("organization") or ""),
                date_text=str(tool_args.get("date_text") or ""),
                document_type=str(tool_args.get("document_type") or "white-paper"),
                header_text=str(tool_args.get("header_text") or ""),
                document_number=str(tool_args.get("document_number") or ""),
                attachments=list(tool_args.get("attachments") or []),
                images=list(tool_args.get("images") or []),
                tables=list(tool_args.get("tables") or []),
            )
            export = prepare_workspace_export(
                workspace_root,
                result["path"],
                max_file_bytes=max_file_bytes,
            )
            return result, [export]

        if tool_name == "skill_get_metadata":
            return (
                get_skill_metadata(installed_root, str(tool_args.get("skill_name") or "")),
                [],
            )

        if tool_name == "skill_list_files":
            return (
                list_skill_files(
                    installed_root,
                    str(tool_args.get("skill_name") or ""),
                    int(tool_args.get("max_depth") or 3),
                ),
                [],
            )

        if tool_name == "skill_read_file":
            return (
                read_skill_file(
                    installed_root,
                    str(tool_args.get("skill_name") or ""),
                    str(tool_args.get("relative_path") or ""),
                    int(tool_args.get("max_chars") or 12000),
                ),
                [],
            )

        if tool_name == "skill_run_command":
            if not params.allow_skill_commands:
                return (
                    {
                        "error": (
                            "skill_run_command is disabled. "
                            "Enable Allow Skill Commands to use it."
                        )
                    },
                    [],
                )
            return (
                run_skill_command(
                    installed_root,
                    skill_name=str(tool_args.get("skill_name") or ""),
                    command=tool_args.get("command"),
                    cwd_relative=tool_args.get("cwd_relative"),
                    allowed_commands=params.allowed_commands,
                ),
                [],
            )

        if tool_name == "runtime_list_files":
            return list_workspace_files(
                workspace_root,
                int(tool_args.get("max_depth") or 4),
            ), []

        if tool_name == "runtime_read_file":
            return (
                read_workspace_file(
                    workspace_root,
                    relative_path=str(tool_args.get("relative_path") or ""),
                    encoding=str(tool_args.get("encoding") or "utf-8"),
                    max_chars=int(tool_args.get("max_chars") or 12000),
                ),
                [],
            )

        if tool_name == "runtime_write_file":
            return (
                write_workspace_file(
                    workspace_root,
                    relative_path=str(tool_args.get("relative_path") or ""),
                    content=str(tool_args.get("content") or ""),
                    encoding=str(tool_args.get("encoding") or "utf-8"),
                    append=bool(tool_args.get("append", False)),
                    max_file_bytes=max_file_bytes,
                ),
                [],
            )

        if tool_name == "runtime_run_python":
            if not params.allow_runtime_execution:
                return (
                    {
                        "error": (
                            "runtime execution is disabled. "
                            "Enable Allow Runtime Execution to use it."
                        )
                    },
                    [],
                )
            return (
                run_workspace_python(
                    workspace_root,
                    code=str(tool_args.get("code") or ""),
                    script_name=str(tool_args.get("script_name") or "generated_script.py"),
                    timeout=int(
                        tool_args.get("timeout")
                        or params.runtime_command_timeout
                        or 60
                    ),
                ),
                [],
            )

        if tool_name == "runtime_run_command":
            if not params.allow_runtime_execution:
                return (
                    {
                        "error": (
                            "runtime execution is disabled. "
                            "Enable Allow Runtime Execution to use it."
                        )
                    },
                    [],
                )
            return (
                run_workspace_command(
                    workspace_root,
                    command=tool_args.get("command"),
                    cwd_relative=tool_args.get("cwd_relative"),
                    allowed_commands=params.runtime_allowed_commands,
                    timeout=int(
                        tool_args.get("timeout")
                        or params.runtime_command_timeout
                        or 60
                    ),
                ),
                [],
            )

        if tool_name == "runtime_export_file":
            export = prepare_workspace_export(
                workspace_root,
                str(tool_args.get("relative_path") or ""),
                max_file_bytes=max_file_bytes,
            )
            return {"exported": export.to_dict()}, [export]

        return {"error": f"unknown internal tool: {tool_name}"}, []

    def _invoke(self, parameters: Dict[str, Any]) -> Generator[AgentInvokeMessage, None, None]:
        params = SkillAgentParams(**parameters)
        storage = self.session.storage

        with tempfile.TemporaryDirectory(prefix="agent-skill-runtime-") as runtime_dir:
            installed_root = Path(runtime_dir) / "installed"
            workspace_root = Path(runtime_dir) / "workspace"
            workspace_root.mkdir(parents=True, exist_ok=True)

            skill_package_items = self._normalize_file_items(params.skill_packages)
            if skill_package_items:
                try:
                    installed = install_skill_files(storage, skill_package_items, overwrite=True)
                    if params.debug_mode:
                        names = ", ".join(str(item.get("name")) for item in installed)
                        yield self.create_text_message(f"Installed uploaded skill package(s): {names}\n")
                except Exception as exc:
                    yield self.create_text_message(f"Failed to install uploaded skill package(s): {exc}\n")

            registry, builtin_count, external_count, installed_count, skill_sources = self._load_registry(
                storage,
                installed_root,
                params.external_skills_dir,
            )

            if params.debug_mode:
                all_skill_names = registry.list_skill_names()
                yield self.create_text_message(
                    f"Loaded {len(all_skill_names)} skill(s): "
                    f"{builtin_count} built-in, {external_count} external, "
                    f"{installed_count} installed. "
                    f"{', '.join(all_skill_names) if all_skill_names else 'none'}\n"
                )

            if params.custom_skills:
                names_before_custom = set(registry.list_skill_names())
                custom_count, error_msg = registry.register_from_yaml(params.custom_skills)
                for name in registry.list_skill_names():
                    if name not in names_before_custom:
                        skill_sources[name] = "custom"
                if error_msg:
                    yield self.create_text_message(f"Custom skills error: {error_msg}\n")
                elif params.debug_mode:
                    yield self.create_text_message(f"Loaded {custom_count} custom skill(s).\n")

            skill_filter = self._parse_enabled_skills(params.enabled_skills)
            max_active_skills = max(1, min(int(params.max_active_skills or 3), 10))
            model_config = self._to_llm_model_config(params.model)
            primary_query = self._extract_primary_query(params.query) or str(params.query or "")
            history_messages, memory_turn_count = self._prepare_history_messages(
                params.model,
                params.query,
                max(0, min(int(params.history_turns or 0), 100)),
            )
            routing_context = self._build_routing_context(
                history_messages,
                primary_query,
            )
            keyword_matches = registry.match_query(
                query=primary_query,
                skill_filter=skill_filter,
                max_skills=max_active_skills,
            )
            selected_names = [match.skill.config.name for match in keyword_matches]
            semantic_matches: list[dict[str, Any]] = []

            if not selected_names and params.semantic_skill_matching:
                try:
                    semantic_matches = self._semantic_match_skills(
                        model_config,
                        routing_context,
                        self._skill_inventory(registry, skill_sources, skill_filter),
                        max_active_skills,
                    )
                    selected_names = [match["name"] for match in semantic_matches]
                except Exception as exc:
                    if params.debug_mode:
                        yield self.create_text_message(f"Semantic skill matching failed: {exc}\n")

            skill_prompt, activated_skills = self._format_selected_skills(
                registry,
                primary_query,
                selected_names,
            )

            system_parts = [self.BASE_SYSTEM_PROMPT]
            inventory = self._skill_inventory(registry, skill_sources, skill_filter)
            if inventory:
                system_parts.append("\n\n# Available Skills\n")
                for item in inventory:
                    system_parts.append(
                        f"- {item['name']} [{item['source']}]: {item['description']}\n"
                    )
                system_parts.append(
                    "\nWhen the user asks which skills are available, answer from this list. "
                    "Do not say the skill list is empty.\n"
                )
            if skill_prompt:
                system_parts.append("\n\n" + skill_prompt)
            if activated_skills and params.debug_mode:
                route = "trigger" if keyword_matches else "semantic"
                yield self.create_text_message(
                    f"Activated skills ({route}): {', '.join(activated_skills)}\n"
                )
                if semantic_matches:
                    details = "; ".join(
                        f"{item['name']}={item['confidence']:.2f} ({item['reason']})"
                        for item in semantic_matches
                    )
                    yield self.create_text_message(f"Semantic matches: {details}\n\n")
                else:
                    yield self.create_text_message("\n")
            elif params.debug_mode:
                yield self.create_text_message(
                    f"No skills matched query: {primary_query[:100]}\n\n"
                )

            installed_infos = list_installed_skills(storage)
            if installed_infos:
                system_parts.append("\n\n# Installed Skill Packages\n")
                for item in installed_infos:
                    system_parts.append(
                        f"- {item.get('name')}: {item.get('description') or ''}\n"
                    )
                system_parts.append(
                    "\nUse skill_get_metadata before reading files or running commands from a package.\n"
                )

            if params.allow_runtime_execution:
                system_parts.append(
                    "\n\n# Runtime Workspace\n"
                    "Runtime execution is enabled for this invocation. Use runtime_run_python "
                    "for generated Python and runtime_run_command only for allowlisted executables. "
                    "All paths must be relative to the temporary workspace. After creating a "
                    "deliverable, call runtime_export_file with its relative path.\n"
                )
            else:
                system_parts.append(
                    "\n\n# Runtime Workspace\n"
                    "Runtime command execution is disabled for this invocation. You may still use "
                    "runtime_write_file, runtime_read_file, runtime_list_files, and "
                    "runtime_export_file. Do not claim that code was executed when it was not.\n"
                )

            if params.debug_mode:
                yield self.create_text_message(
                    f"Memory: loaded {memory_turn_count} turn(s), "
                    f"{len(history_messages)} message(s).\n"
                )

            messages: List[PromptMessage] = [
                SystemPromptMessage(content="".join(system_parts)),
                *history_messages,
                UserPromptMessage(content=params.query),
            ]

            model_label = str(self._safe_get(model_config, "model", default="model") or "model")
            model_provider = str(self._safe_get(model_config, "provider", default="") or "")

            tool_instances = {
                self._tool_identity_name(tool): tool
                for tool in params.tools or []
                if self._tool_identity_name(tool)
            }
            tool_defs = self._build_tool_definitions(
                params.tools,
                include_skill_commands=params.allow_skill_commands,
                include_runtime_execution=params.allow_runtime_execution,
            )

            iteration = 0
            exported_paths: set[str] = set()
            knowledge_citations: list[dict[str, Any]] = []
            saved_tool_blob_count = 0
            max_file_bytes = max(
                1,
                min(int(params.runtime_max_file_mb or 20), 100),
            ) * 1024 * 1024
            finished_normally = False
            while iteration < params.maximum_iterations:
                iteration += 1

                iteration_started = time.perf_counter()
                iteration_log = self.create_log_message(
                    label=f"Iteration {iteration}",
                    data={"iteration": iteration},
                    metadata={"started_at": iteration_started},
                    status=ToolInvokeMessage.LogMessage.LogStatus.START,
                )
                yield iteration_log

                model_started = time.perf_counter()
                model_log = self.create_log_message(
                    label=f"{model_label} Thinking",
                    data={},
                    metadata={"provider": model_provider, "started_at": model_started},
                    status=ToolInvokeMessage.LogMessage.LogStatus.START,
                    parent=iteration_log,
                )
                yield model_log

                try:
                    response_text = ""
                    tool_calls: list[tuple[str, str, dict[str, Any]]] = []

                    chunks = self.session.model.llm.invoke(
                        model_config=model_config,
                        prompt_messages=messages,
                        tools=tool_defs if tool_defs else None,
                        stop=model_config.completion_params.get("stop", [])
                        if getattr(model_config, "completion_params", None)
                        else [],
                        stream=True,
                    )

                    for chunk in chunks:
                        delta = getattr(chunk, "delta", None)
                        message = getattr(delta, "message", None) if delta is not None else None
                        message = message or delta or chunk

                        content = getattr(message, "content", None)
                        if isinstance(content, list):
                            for item in content:
                                text = getattr(item, "data", None) or getattr(item, "text", None) or str(item)
                                if text:
                                    response_text += text
                                    yield self.create_text_message(text)
                        elif isinstance(content, str) and content:
                            response_text += content
                            yield self.create_text_message(content)

                        extracted = self._extract_tool_calls(message)
                        if extracted:
                            tool_calls.extend(extracted)

                    yield self.finish_log_message(
                        log=model_log,
                        data={"response_length": len(response_text), "has_tool_calls": bool(tool_calls)},
                        metadata={
                            "finished_at": time.perf_counter(),
                            "elapsed_time": time.perf_counter() - model_started,
                        },
                    )

                    if not tool_calls:
                        citation_appendix = self._missing_knowledge_citation_appendix(
                            response_text,
                            knowledge_citations,
                        )
                        if citation_appendix:
                            yield self.create_text_message(citation_appendix)
                        finished_normally = True
                        yield self.finish_log_message(
                            log=iteration_log,
                            data={"status": "completed", "response": response_text[:200]},
                            metadata={
                                "finished_at": time.perf_counter(),
                                "elapsed_time": time.perf_counter() - iteration_started,
                            },
                        )
                        break

                    messages.append(
                        AssistantPromptMessage(
                            content=response_text,
                            tool_calls=self._assistant_tool_call_objects(tool_calls),
                        )
                    )

                    for tool_call_id, tool_name, tool_args in tool_calls:
                        tool_started = time.perf_counter()
                        tool_log = self.create_log_message(
                            label=f"Tool: {tool_name}",
                            data={"arguments": tool_args},
                            metadata={"started_at": tool_started},
                            status=ToolInvokeMessage.LogMessage.LogStatus.START,
                            parent=iteration_log,
                        )
                        yield tool_log

                        try:
                            if tool_name in self.INTERNAL_TOOL_NAMES:
                                internal_result, internal_exports = self._execute_internal_tool(
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                    storage=storage,
                                    installed_root=installed_root,
                                    workspace_root=workspace_root,
                                    params=params,
                                    registry=registry,
                                    skill_sources=skill_sources,
                                )
                                tool_result = json.dumps(internal_result, ensure_ascii=False)
                            else:
                                if tool_name not in tool_instances:
                                    raise ValueError(f"Unknown tool: {tool_name}")
                                tool_instance = tool_instances[tool_name]
                                tool_result_parts = []
                                provider_type = ToolProviderType(self._tool_provider_type(tool_instance))
                                for result in self.session.tool.invoke(
                                    provider_type=provider_type,
                                    provider=self._tool_identity_provider(tool_instance),
                                    tool_name=self._tool_identity_name(tool_instance),
                                    parameters={**self._tool_runtime_parameters(tool_instance), **tool_args},
                                ):
                                    if (
                                        getattr(result, "type", None)
                                        == ToolInvokeMessage.MessageType.BLOB
                                        and hasattr(getattr(result, "message", None), "blob")
                                    ):
                                        saved_tool_blob_count += 1
                                        meta = getattr(result, "meta", None) or {}
                                        filename = ""
                                        mime_type = ""
                                        if isinstance(meta, dict):
                                            filename = str(meta.get("filename") or "")
                                            mime_type = str(meta.get("mime_type") or "")
                                        if not filename:
                                            suffix = {
                                                "image/jpeg": ".jpg",
                                                "image/png": ".png",
                                                "image/webp": ".webp",
                                                "image/gif": ".gif",
                                            }.get(mime_type, ".bin")
                                            filename = f"{tool_name}-{saved_tool_blob_count}{suffix}"
                                        saved_blob = save_workspace_blob(
                                            workspace_root,
                                            data=result.message.blob,
                                            filename=filename,
                                            max_file_bytes=max_file_bytes,
                                        )
                                        tool_result_parts.append(
                                            "Tool file saved in runtime workspace: "
                                            f"{saved_blob['path']}"
                                        )
                                        yield self.create_blob_message(
                                            blob=result.message.blob,
                                            meta=getattr(result, "meta", None),
                                        )
                                    text = self._stringify_tool_message(result)
                                    if text:
                                        tool_result_parts.append(text)
                                tool_result = "\n".join(tool_result_parts) or "Tool executed successfully."
                                if tool_name == "getKonwledgeBase":
                                    new_citations = self._extract_knowledge_citations(tool_result)
                                    self._merge_knowledge_citations(
                                        knowledge_citations,
                                        new_citations,
                                    )
                                    tool_result += self._knowledge_citation_hint(new_citations)

                            yield self.finish_log_message(
                                log=tool_log,
                                data={"result": tool_result[:500]},
                                metadata={
                                    "finished_at": time.perf_counter(),
                                    "elapsed_time": time.perf_counter() - tool_started,
                                },
                            )

                            if tool_name in self.INTERNAL_TOOL_NAMES:
                                for export in internal_exports:
                                    if export.relative_path in exported_paths:
                                        continue
                                    yield self.create_blob_message(
                                        blob=export.absolute_path.read_bytes(),
                                        meta={
                                            "mime_type": export.mime_type,
                                            "filename": export.filename,
                                        },
                                    )
                                    exported_paths.add(export.relative_path)

                            messages.append(
                                ToolPromptMessage(
                                    content=tool_result,
                                    tool_call_id=tool_call_id,
                                    name=tool_name,
                                )
                            )

                        except Exception as exc:
                            error_msg = f"Tool error: {exc}"
                            yield self.finish_log_message(
                                log=tool_log,
                                data={"error": error_msg},
                                metadata={"finished_at": time.perf_counter()},
                                status=ToolInvokeMessage.LogMessage.LogStatus.ERROR,
                            )
                            messages.append(
                                ToolPromptMessage(
                                    content=error_msg,
                                    tool_call_id=tool_call_id,
                                    name=tool_name,
                                )
                            )

                    yield self.finish_log_message(
                        log=iteration_log,
                        data={"status": "tool_calls_completed", "tools_called": [tc[1] for tc in tool_calls]},
                        metadata={
                            "finished_at": time.perf_counter(),
                            "elapsed_time": time.perf_counter() - iteration_started,
                        },
                    )

                except Exception as exc:
                    yield self.finish_log_message(
                        log=model_log,
                        data={"error": str(exc)},
                        metadata={"finished_at": time.perf_counter()},
                        status=ToolInvokeMessage.LogMessage.LogStatus.ERROR,
                    )
                    yield self.create_text_message(f"\n\nError: {exc}")
                    break

            if params.auto_export_files:
                max_file_bytes = max(
                    1,
                    min(int(params.runtime_max_file_mb or 20), 100),
                ) * 1024 * 1024
                for export in collect_exportable_files(
                    workspace_root,
                    max_files=10,
                    max_file_bytes=max_file_bytes,
                ):
                    if export.relative_path in exported_paths:
                        continue
                    yield self.create_blob_message(
                        blob=export.absolute_path.read_bytes(),
                        meta={
                            "mime_type": export.mime_type,
                            "filename": export.filename,
                        },
                    )
                    exported_paths.add(export.relative_path)

            if iteration >= params.maximum_iterations and not finished_normally:
                yield self.create_text_message(
                    f"\n\nReached maximum iterations ({params.maximum_iterations})."
                )
