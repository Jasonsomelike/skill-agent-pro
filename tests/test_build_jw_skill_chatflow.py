import unittest
from pathlib import Path

import yaml

from scripts.build_jw_skill_chatflow import AGENT_ID, build


class BuildJwSkillChatflowTests(unittest.TestCase):
    def test_build_keeps_new_tools_and_binds_all_memory_user_ids(self):
        source_path = Path("chatflows/JW-SkillAgent-Pro-draft-source.yml")
        source = yaml.safe_load(source_path.read_text(encoding="utf-8"))

        result = build(source)

        agent = next(
            node
            for node in result["workflow"]["graph"]["nodes"]
            if node["id"] == AGENT_ID
        )
        tools = agent["data"]["agent_parameters"]["tools"]["value"]
        by_name = {tool["tool_name"]: tool for tool in tools}
        self.assertEqual(
            set(by_name),
            {
                "getKonwledgeBase",
                "list_memory",
                "add_memory",
                "update_memory",
                "anspire_search",
                "anspire_crawl",
                "text2image",
                "bilibili_search",
                "bilibili_get_video_info",
            },
        )

        for name in ("list_memory", "add_memory", "update_memory"):
            user_id = by_name[name]["parameters"]["user_id"]
            self.assertEqual(
                user_id,
                {
                    "auto": 0,
                    "value": {
                        "type": "variable",
                        "value": ["sys", "user_id"],
                    },
                },
            )

        identifiers = {
            (
                item["value"].get("plugin_unique_identifier")
                or item["value"].get("marketplace_plugin_unique_identifier")
            )
            for item in result["dependencies"]
        }
        self.assertTrue(any("seedream_aigc:0.0.2@" in item for item in identifiers))
        self.assertTrue(any("bilibili_search:0.0.3@" in item for item in identifiers))


if __name__ == "__main__":
    unittest.main()
