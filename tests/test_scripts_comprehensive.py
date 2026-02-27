import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import convert_doc
from scripts import report_generator
from scripts import session_manager


ROOT_DIR = Path(__file__).resolve().parents[1]


class ComprehensiveScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="dv-script-tests-")
        cls.sandbox_root = Path(cls.temp_dir.name).resolve()
        cls.temp_scripts_dir = cls.sandbox_root / "scripts"
        cls.temp_scripts_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def _session_base_dirs(self):
        base = self.temp_scripts_dir.parent / "data"
        (base / "sessions").mkdir(parents=True, exist_ok=True)
        (base / "reports").mkdir(parents=True, exist_ok=True)
        return base

    def test_session_manager_core_workflow(self):
        self._session_base_dirs()
        with patch.object(session_manager, "get_script_dir", return_value=self.temp_scripts_dir):
            session_id = session_manager.create_session("脚本测试会话")
            self.assertTrue(session_id.startswith("dv-"))

            session = session_manager.get_session(session_id)
            self.assertIsInstance(session, dict)
            self.assertEqual(session["topic"], "脚本测试会话")
            self.assertTrue(session["dimensions"])
            first_dimension = list(session["dimensions"].keys())[0]

            add_ok = session_manager.add_interview_log(
                session_id=session_id,
                question="你目前的痛点是什么？",
                answer="流程效率低",
                dimension=first_dimension,
            )
            self.assertTrue(add_ok)

            up_ok = session_manager.update_dimension_coverage(
                session_id=session_id,
                dimension=first_dimension,
                coverage=60,
                items=[{"name": "流程效率低"}],
            )
            self.assertTrue(up_ok)

            progress = session_manager.get_progress_display(session_id)
            self.assertIn("访谈进度", progress)
            self.assertIn("60%", progress)

            self.assertTrue(session_manager.pause_session(session_id))
            paused = session_manager.get_session(session_id)
            self.assertEqual(paused["status"], "paused")

            self.assertTrue(session_manager.resume_session(session_id))
            resumed = session_manager.get_session(session_id)
            self.assertEqual(resumed["status"], "in_progress")

            self.assertTrue(session_manager.complete_session(session_id))
            completed = session_manager.get_session(session_id)
            self.assertEqual(completed["status"], "completed")

            sessions = session_manager.list_sessions()
            ids = [item["session_id"] for item in sessions]
            self.assertIn(session_id, ids)

            incomplete = session_manager.get_incomplete_sessions()
            self.assertNotIn(session_id, incomplete)

            self.assertTrue(session_manager.delete_session(session_id))
            self.assertIsNone(session_manager.get_session(session_id))

    def test_report_generator_generate_report(self):
        base = self._session_base_dirs()
        session_id = "dv-test-report-001"
        session_file = base / "sessions" / f"{session_id}.json"
        session_payload = {
            "session_id": session_id,
            "topic": "报告脚本测试",
            "created_at": "2026-02-23T00:00:00Z",
            "updated_at": "2026-02-23T00:00:00Z",
            "status": "completed",
            "dimensions": {
                "customer_needs": {
                    "coverage": 100,
                    "items": [{"name": "提升效率"}],
                },
                "business_process": {
                    "coverage": 60,
                    "items": [{"name": "审批流程优化"}],
                },
                "tech_constraints": {"coverage": 40, "items": []},
                "project_constraints": {"coverage": 20, "items": []},
            },
            "interview_log": [
                {"question": "Q1", "answer": "A1", "dimension": "customer_needs"},
                {"question": "Q2", "answer": "A2", "dimension": "business_process"},
            ],
            "requirements": [{"title": "提升效率", "priority": "高", "type": "功能"}],
            "summary": "测试摘要",
        }
        session_file.write_text(json.dumps(session_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        with patch.object(report_generator, "get_script_dir", return_value=self.temp_scripts_dir):
            generated_path = report_generator.generate_report(session_id)
            self.assertIsNotNone(generated_path)

            output_path = Path(generated_path)
            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("访谈报告", content)
            self.assertIn("报告脚本测试", content)

            preview = report_generator.generate_simple_report(session_payload)
            self.assertIn("需求摘要", preview)
            self.assertIn("详细需求分析", preview)

    def test_convert_doc_txt_batch_and_cleanup(self):
        base = self._session_base_dirs()
        input_dir = self.sandbox_root / "inputs"
        input_dir.mkdir(parents=True, exist_ok=True)

        txt_file = input_dir / "a.txt"
        md_file = input_dir / "b.md"
        unsupported_file = input_dir / "c.unsupported"
        txt_file.write_text("hello txt", encoding="utf-8")
        md_file.write_text("# hello md", encoding="utf-8")
        unsupported_file.write_text("x", encoding="utf-8")

        with patch.object(convert_doc, "get_script_dir", return_value=self.temp_scripts_dir):
            txt_out = convert_doc.convert_document(str(txt_file))
            self.assertIsNotNone(txt_out)
            txt_out_path = Path(txt_out)
            self.assertTrue(txt_out_path.exists())
            self.assertEqual(txt_out_path.read_text(encoding="utf-8"), "hello txt")

            unsupported = convert_doc.convert_document(str(unsupported_file))
            self.assertIsNone(unsupported)

            batch_result = convert_doc.batch_convert(str(input_dir))
            self.assertEqual(batch_result["total"], 3)
            self.assertEqual(batch_result["success"], 2)
            self.assertEqual(batch_result["failed"], 1)

            temp_dir = base / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            (temp_dir / "temp-file.tmp").write_text("tmp", encoding="utf-8")
            self.assertTrue(temp_dir.exists())
            convert_doc.cleanup()
            self.assertFalse(temp_dir.exists())

    def test_cli_help_commands(self):
        commands = [
            ["python3", "scripts/session_manager.py", "--help"],
            ["python3", "scripts/convert_doc.py", "--help"],
            ["python3", "scripts/report_generator.py", "--help"],
        ]
        for cmd in commands:
            completed = subprocess.run(
                cmd,
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, f"command failed: {' '.join(cmd)}")
            self.assertIn("usage", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
