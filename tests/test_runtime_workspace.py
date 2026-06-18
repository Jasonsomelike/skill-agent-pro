import tempfile
import unittest
from pathlib import Path

from skills.runtime_workspace import (
    collect_exportable_files,
    prepare_workspace_export,
    read_workspace_file,
    run_workspace_python,
    safe_workspace_path,
    write_workspace_file,
)


class RuntimeWorkspaceTests(unittest.TestCase):
    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(RuntimeError):
                safe_workspace_path(Path(temp_dir), "../escape.txt")

    def test_write_and_read_text_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = write_workspace_file(
                root,
                relative_path="output/result.txt",
                content="hello",
            )
            self.assertEqual(result["size"], 5)
            loaded = read_workspace_file(root, relative_path="output/result.txt")
            self.assertEqual(loaded["content"], "hello")

    def test_python_execution_creates_workspace_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result = run_workspace_python(
                root,
                code="from pathlib import Path\nPath('answer.txt').write_text('111', encoding='utf-8')",
            )
            self.assertEqual(result["returncode"], 0)
            self.assertEqual((root / "answer.txt").read_text(encoding="utf-8"), "111")

    def test_export_metadata_and_auto_collection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_workspace_file(root, relative_path="report.pdf", content="fake")
            export = prepare_workspace_export(root, "report.pdf")
            self.assertEqual(export.mime_type, "application/pdf")
            exports = collect_exportable_files(root)
            self.assertEqual([item.relative_path for item in exports], ["report.pdf"])


if __name__ == "__main__":
    unittest.main()
