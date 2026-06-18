import json
import unittest

from dify_plugin.entities.model.message import (
    DocumentPromptMessageContent,
    TextPromptMessageContent,
    UserPromptMessage,
)

from strategies.skill_agent import SkillAgentAgentStrategy


class SkillAgentHistoryTests(unittest.TestCase):
    def setUp(self):
        self.strategy = object.__new__(SkillAgentAgentStrategy)

    def test_normalize_history_message_flattens_multimodal_content_to_text(self):
        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="请根据这份讲义继续讲解"),
                DocumentPromptMessageContent(
                    format="pdf",
                    mime_type="application/pdf",
                    filename="mac-frame.pdf",
                    url="https://example.com/page_29.pdf",
                    base64_data="very-secret-base64",
                ),
            ]
        )

        normalized = self.strategy._normalize_history_message(message)

        self.assertIsInstance(normalized, UserPromptMessage)
        self.assertIsInstance(normalized.content, str)
        self.assertIn("请根据这份讲义继续讲解", normalized.content)
        self.assertIn("mac-frame.pdf", normalized.content)
        self.assertNotIn("very-secret-base64", normalized.content)
        json.dumps(normalized.model_dump(mode="json"), ensure_ascii=False)

    def test_normalize_history_message_supports_dict_multimodal_content(self):
        raw_message = {
            "role": "assistant",
            "content": [
                {"type": "text", "data": "我记得你上次学到 MAC 帧。"},
                {
                    "type": "document",
                    "filename": "network-notes.pdf",
                    "url": "data:application/pdf;base64,AAAA",
                },
            ],
        }

        normalized = self.strategy._normalize_history_message(raw_message)

        self.assertEqual(normalized.content, "我记得你上次学到 MAC 帧。\n[document: network-notes.pdf]")

    def test_prepare_history_messages_removes_wrapped_duplicate_query(self):
        history = [UserPromptMessage(content="现在呢")]
        model = {"history_prompt_messages": history}
        wrapped_query = "用户请求：\n现在呢\n\n用户 ID：abc123\n\n图片解析（没有图片时为空）：\n"

        normalized_history, turn_count = self.strategy._prepare_history_messages(
            model=model,
            query=wrapped_query,
            max_turns=10,
        )

        self.assertEqual(normalized_history, [])
        self.assertEqual(turn_count, 0)


if __name__ == "__main__":
    unittest.main()
