"""Build the streamlined JW Skill Agent Pro Dify Chatflow DSL."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import yaml


LOCAL_PLUGIN = (
    "local/agent-skill-plugin-plus:1.5.1@"
    "831a912c4b5028dc0e313023487b7c67c95684feba47dc1cf230081b38275ef9"
)
DEEPSEEK_PLUGIN = (
    "langgenius/deepseek:0.0.15@"
    "725407927b04e236212083d20e92830d60fa944e42cd357ef6902c160414f6f1"
)
TONGYI_PLUGIN = (
    "langgenius/tongyi:0.1.45@"
    "7f2b2d5b163de4c1ad8fad80e624c08d47ed7942a6a534e88e5786e65073f3ca"
)
ANSPIRE_PLUGIN = (
    "anspire/anspire_search:0.1.2@"
    "39b5bc58ad26d618669d4b6ba865d11c8174e7dfea0fd361a2757a0f05b47bc8"
)
BAILIAN_MEMORY_PLUGIN = (
    "langgenius/bailian_memory:0.0.7@"
    "129745df48663b5d877417ccc89d9f370cdc4cc0a4dabba4b1b62da129995819"
)

START_ID = "1711528708197"
FILE_BRANCH_ID = "1780798147131"
VISION_LLM_ID = "17807981172390"
VISION_ASSIGN_ID = "1780799440648"
CLEAR_VISION_ID = "skill-clear-vision"
AGENT_ID = "1780803518766"
ANSWER_ID = "1780668375718"


def dependency(plugin_identifier: str, *, local_package: bool = False) -> dict:
    if local_package:
        return {
            "current_identifier": None,
            "type": "package",
            "value": {
                "plugin_unique_identifier": plugin_identifier,
                "version": "1.5.1",
            },
        }
    return {
        "current_identifier": None,
        "type": "marketplace",
        "value": {
            "marketplace_plugin_unique_identifier": plugin_identifier,
            "version": None,
        },
    }


def edge(source: str, target: str, source_type: str, target_type: str, handle: str = "source") -> dict:
    return {
        "data": {
            "isInIteration": False,
            "isInLoop": False,
            "sourceType": source_type,
            "targetType": target_type,
        },
        "id": f"{source}-{handle}-{target}-target",
        "selected": False,
        "source": source,
        "sourceHandle": handle,
        "target": target,
        "targetHandle": "target",
        "type": "custom",
        "zIndex": 0,
    }


def manual_variable(selector: list[str]) -> dict:
    return {
        "auto": 0,
        "value": {
            "type": "variable",
            "value": selector,
        },
    }


def manual_constant(value: object) -> dict:
    return {
        "auto": 0,
        "value": {
            "type": "constant",
            "value": value,
        },
    }


def configure_memory_tool(tool: dict) -> dict:
    tool = deepcopy(tool)
    name = tool.get("tool_name")
    params = tool.setdefault("parameters", {})
    if name == "list_memory":
        params["page_num"] = manual_constant(1)
        params["page_size"] = manual_constant(50)
        params["user_id"] = manual_variable(["sys", "user_id"])
    elif name in {"add_memory", "update_memory"}:
        params["user_id"] = manual_variable(["sys", "user_id"])
    return tool


def find_node(nodes: list[dict], node_id: str) -> dict:
    return deepcopy(next(node for node in nodes if node["id"] == node_id))


def load_tools(nodes: list[dict]) -> list[dict]:
    main_agent = next(node for node in nodes if node["id"] == AGENT_ID)
    memory_agent = next(node for node in nodes if node["id"] == "1781090448061")
    available = {}
    for tool in main_agent["data"]["agent_parameters"]["tools"]["value"]:
        available[tool["tool_name"]] = tool
    for tool in memory_agent["data"]["agent_parameters"]["tools"]["value"]:
        available[tool["tool_name"]] = tool

    selected_names = [
        "getKonwledgeBase",
        "list_memory",
        "add_memory",
        "update_memory",
        "anspire_search",
        "anspire_crawl",
    ]
    missing = [name for name in selected_names if name not in available]
    if missing:
        raise RuntimeError(f"source Chatflow is missing tools: {missing}")
    return [configure_memory_tool(available[name]) for name in selected_names]


def build_agent_node(source_nodes: list[dict]) -> dict:
    node = find_node(source_nodes, AGENT_ID)
    node["data"] = {
        "agent_parameters": {
            "model": {
                "type": "constant",
                "value": {
                    "completion_params": {
                        "temperature": 0.35,
                    },
                    "mode": "chat",
                    "model": "deepseek-v4-pro",
                    "model_type": "llm",
                    "provider": "langgenius/deepseek/deepseek",
                    "type": "model-selector",
                },
            },
            "tools": {
                "type": "constant",
                "value": load_tools(source_nodes),
            },
            "query": {
                "type": "constant",
                "value": (
                    "用户请求：\n{{#sys.query#}}\n\n"
                    "图片解析（没有图片时为空）：\n{{#conversation.vision#}}"
                ),
            },
            "enabled_skills": {"type": "constant", "value": "all"},
            "custom_skills": {"type": "constant", "value": ""},
            "skill_packages": {"type": "constant", "value": []},
            "external_skills_dir": {
                "type": "constant",
                "value": "/opt/dify-agent-skills",
            },
            "debug_mode": {"type": "constant", "value": False},
            "max_active_skills": {"type": "constant", "value": 3},
            "semantic_skill_matching": {"type": "constant", "value": True},
            "history_turns": {"type": "constant", "value": 30},
            "allow_skill_commands": {"type": "constant", "value": False},
            "allowed_commands": {
                "type": "constant",
                "value": "python,python3,node,npm,npx,bun,sh,bash",
            },
            "allow_runtime_execution": {"type": "constant", "value": False},
            "runtime_allowed_commands": {
                "type": "constant",
                "value": "python,python3",
            },
            "runtime_command_timeout": {"type": "constant", "value": 60},
            "runtime_max_file_mb": {"type": "constant", "value": 20},
            "auto_export_files": {"type": "constant", "value": True},
            "maximum_iterations": {"type": "constant", "value": 20},
        },
        "agent_strategy_label": "Skill-based Agent",
        "agent_strategy_name": "skill_agent",
        "agent_strategy_provider_name": "local/agent-skill-plugin-plus/agent_skill_provider",
        "desc": "由外部 Skills 路由问候、教学、解题、批改、出题、学习建议与边界处理。",
        "memory": {
            "query_prompt_template": "{{#sys.query#}}\n\n{{#sys.files#}}",
            "window": {
                "enabled": True,
                "size": 30,
            },
        },
            "meta": {
                "minimum_dify_version": "1.7.0",
                "version": "1.5.1",
            },
        "output_schema": {},
        "plugin_unique_identifier": LOCAL_PLUGIN,
        "selected": False,
        "title": "Skill 学习 Agent",
        "tool_node_version": "2",
        "type": "agent",
    }
    node["height"] = 186
    node["position"] = {"x": 1000, "y": 360}
    node["positionAbsolute"] = dict(node["position"])
    return node


def build_clear_vision_node() -> dict:
    return {
        "data": {
            "items": [
                {
                    "input_type": "constant",
                    "operation": "over-write",
                    "value": "",
                    "variable_selector": ["conversation", "vision"],
                }
            ],
            "selected": False,
            "title": "清空图片上下文",
            "type": "assigner",
            "version": "2",
        },
        "height": 82,
        "id": CLEAR_VISION_ID,
        "position": {"x": 670, "y": 580},
        "positionAbsolute": {"x": 670, "y": 580},
        "selected": False,
        "sourcePosition": "right",
        "targetPosition": "left",
        "type": "custom",
        "width": 241,
    }


def build(source: dict) -> dict:
    result = deepcopy(source)
    result["app"]["name"] = "JW页分版-SkillAgent-Pro"
    result["app"]["description"] = (
        "计算机网络学习 Chatflow：Skill 自动路由、长期学习记忆、图片理解、"
        "知识库优先与下一步学习建议。"
    )
    result["dependencies"] = [
        dependency(LOCAL_PLUGIN, local_package=True),
        dependency(DEEPSEEK_PLUGIN),
        dependency(TONGYI_PLUGIN),
        dependency(ANSPIRE_PLUGIN),
        dependency(BAILIAN_MEMORY_PLUGIN),
    ]

    workflow = result["workflow"]
    workflow["conversation_variables"] = [
        {
            "description": "当前轮用户上传图片的结构化解析结果；无图片时主动清空。",
            "id": "ff612829-19ee-4d71-ab16-158b0b87c4d6",
            "name": "vision",
            "selector": ["conversation", "vision"],
            "value": "",
            "value_type": "string",
        }
    ]
    features = workflow["features"]
    features["opening_statement"] = (
        "你好，我是 Skill Agent Pro 计算机网络学习助手。"
        "我可以讲概念、解题、批改、出题，也能根据长期学习记录建议下一步。"
        "你今天想从哪里开始？"
    )
    features["suggested_questions"] = [
        "根据我的学习记录，下一步应该学什么？",
        "给我讲讲 OSI 与 TCP/IP 模型的区别",
        "出 5 道子网划分题考考我",
    ]

    source_nodes = source["workflow"]["graph"]["nodes"]
    start = find_node(source_nodes, START_ID)
    file_branch = find_node(source_nodes, FILE_BRANCH_ID)
    vision = find_node(source_nodes, VISION_LLM_ID)
    vision_assign = find_node(source_nodes, VISION_ASSIGN_ID)
    answer = find_node(source_nodes, ANSWER_ID)

    start["position"] = {"x": 60, "y": 360}
    start["positionAbsolute"] = dict(start["position"])

    file_branch["position"] = {"x": 360, "y": 360}
    file_branch["positionAbsolute"] = dict(file_branch["position"])
    file_branch["data"]["title"] = "是否上传图片"

    vision["position"] = {"x": 670, "y": 120}
    vision["positionAbsolute"] = dict(vision["position"])
    vision["data"]["vision"]["configs"]["variable_selector"] = ["sys", "files"]
    vision["data"]["title"] = "解析网络图片"

    vision_assign["position"] = {"x": 1000, "y": 120}
    vision_assign["positionAbsolute"] = dict(vision_assign["position"])
    vision_assign["data"]["title"] = "保存图片上下文"

    answer["position"] = {"x": 1320, "y": 360}
    answer["positionAbsolute"] = dict(answer["position"])
    answer["data"]["title"] = "学习助手回复"
    answer["data"]["answer"] = f"{{{{#{AGENT_ID}.text#}}}}{{{{#{AGENT_ID}.files#}}}}"

    workflow["graph"] = {
        "edges": [
            edge(START_ID, FILE_BRANCH_ID, "start", "if-else"),
            edge(FILE_BRANCH_ID, VISION_LLM_ID, "if-else", "llm", "true"),
            edge(VISION_LLM_ID, VISION_ASSIGN_ID, "llm", "assigner"),
            edge(VISION_ASSIGN_ID, AGENT_ID, "assigner", "agent"),
            edge(FILE_BRANCH_ID, CLEAR_VISION_ID, "if-else", "assigner", "false"),
            edge(CLEAR_VISION_ID, AGENT_ID, "assigner", "agent"),
            edge(AGENT_ID, ANSWER_ID, "agent", "answer"),
        ],
        "nodes": [
            start,
            file_branch,
            vision,
            vision_assign,
            build_clear_vision_node(),
            build_agent_node(source_nodes),
            answer,
        ],
        "viewport": {
            "x": 20,
            "y": 120,
            "zoom": 0.72,
        },
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = yaml.safe_load(args.source.read_text(encoding="utf-8"))
    output = build(source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
