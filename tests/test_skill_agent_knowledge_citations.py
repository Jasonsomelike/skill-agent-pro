import unittest

from strategies.skill_agent import SkillAgentAgentStrategy


class SkillAgentKnowledgeCitationTests(unittest.TestCase):
    def setUp(self):
        self.strategy = object.__new__(SkillAgentAgentStrategy)

    def test_extracts_split_document_page_and_original_pdf_page(self):
        tool_result = (
            """{"data":{"result":"variable_name='result' variable_value=["""
            "{'content': '\\n\\n![Page 18]"
            "(https://dify.jasonsome.cn:22380/page-images/6c04a9e09b53/page_18.jpg)', "
            """'document_name': '计算机网络（第8版）_谢希仁_part6_p201-240.pdf'}]"}}"""
        )

        citations = self.strategy._extract_knowledge_citations(tool_result)

        self.assertEqual(len(citations), 1)
        self.assertEqual(
            citations[0]["document_name"],
            "计算机网络（第8版）_谢希仁_part6_p201-240.pdf",
        )
        self.assertEqual(citations[0]["local_page"], 18)
        self.assertEqual(citations[0]["original_pdf_page"], 218)

    def test_keeps_each_page_image_paired_with_its_own_record(self):
        tool_result = (
            "variable_name='result' variable_value=["
            "{'content': '![Page 22](https://example.com/page-images/a/page_22.jpg)', "
            "'metadata': {'document_name': 'answers_part12_p441-480.pdf'}}, "
            "{'content': '![Page 18](https://example.com/page-images/b/page_18.jpg)', "
            "'metadata': {'document_name': 'questions_part6_p201-240.pdf'}}"
            "]"
        )

        citations = self.strategy._extract_knowledge_citations(tool_result)

        self.assertEqual(
            [(item["document_name"], item["original_pdf_page"]) for item in citations],
            [
                ("answers_part12_p441-480.pdf", 462),
                ("questions_part6_p201-240.pdf", 218),
            ],
        )

    def test_appends_exact_source_page_and_markdown_image_when_model_omits_them(self):
        citations = [
            {
                "document_name": "计算机网络（第8版）_谢希仁_part6_p201-240.pdf",
                "local_page": 18,
                "original_pdf_page": 218,
                "split_start_page": 201,
                "split_end_page": 240,
                "image_url": (
                    "https://dify.jasonsome.cn:22380/page-images/"
                    "6c04a9e09b53/page_18.jpg"
                ),
            }
        ]

        appendix = self.strategy._missing_knowledge_citation_appendix(
            "教材来源为《计算机网络（第8版）》。",
            citations,
        )

        self.assertIn("计算机网络（第8版）_谢希仁_part6_p201-240.pdf", appendix)
        self.assertIn("原 PDF 第 218 页（分卷内第 18 页）", appendix)
        self.assertIn("![", appendix)
        self.assertIn("page_18.jpg)", appendix)

    def test_does_not_duplicate_exact_source_and_image(self):
        url = "https://example.com/page-images/book/page_18.jpg"
        document_name = "book_part6_p201-240.pdf"
        response = f"来源文件：`{document_name}`\n![Page 18]({url})"
        citations = [
            {
                "document_name": document_name,
                "local_page": 18,
                "original_pdf_page": 218,
                "image_url": url,
            }
        ]

        appendix = self.strategy._missing_knowledge_citation_appendix(
            response,
            citations,
        )

        self.assertEqual(appendix, "")


if __name__ == "__main__":
    unittest.main()
