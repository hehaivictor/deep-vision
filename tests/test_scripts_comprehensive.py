import json
import io
import subprocess
import tempfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch

from scripts import agent_doctor
from scripts import agent_browser_smoke
from scripts import agent_calibration
from scripts import agent_ci_summary
from scripts import agent_contracts
from scripts import agent_autodream
from scripts import agent_doc_gardener
from scripts import agent_eval
from scripts import agent_guardrails
from scripts import agent_harness
from scripts import agent_heartbeat
from scripts import agent_history
from scripts import agent_missions
from scripts import agent_ops
from scripts import agent_observe
from scripts import agent_playbook_sync
from scripts import agent_planner
from scripts import agent_plans
from scripts import agent_profiles
from scripts import agent_scenario_scaffold
from scripts import agent_smoke
from scripts import agent_static_guardrails
from scripts import agent_artifacts
from scripts import agent_workflow
from scripts import context_hub
from scripts import convert_doc
from scripts import migrate_session_evidence_annotations
from scripts import replay_preflight_diagnostics
from scripts import report_generator
from scripts import scenario_loader
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

    def _agent_doctor_env_lines(self, case_name: str) -> list[str]:
        env_root = self.sandbox_root / case_name / "data"
        auth_dir = env_root / "auth"
        scenarios_dir = env_root / "scenarios" / "custom"
        auth_dir.mkdir(parents=True, exist_ok=True)
        scenarios_dir.mkdir(parents=True, exist_ok=True)
        return [
            f"AUTH_DB_PATH={auth_dir / 'users.db'}",
            f"LICENSE_DB_PATH={auth_dir / 'licenses.db'}",
            f"META_INDEX_DB_PATH={env_root / 'meta_index.db'}",
            f"CUSTOM_SCENARIOS_DIR={scenarios_dir}",
        ]

    def _make_harness_execution(
        self,
        *,
        name: str,
        status: str,
        detail: str,
        highlights: list[str] | None = None,
        exit_code: int = 0,
        command: str = "",
        summary: dict | None = None,
        artifact_payload: dict | None = None,
    ):
        result = agent_harness.HarnessStageResult(
            name=name,
            status=status,
            exit_code=exit_code,
            detail=detail,
            command=command,
            highlights=highlights,
            summary=summary,
        )
        return agent_harness.HarnessStageExecution(
            result=result,
            artifact_payload=artifact_payload or {"name": name},
        )

    def _make_sqlite_db(self, path: Path, statements: list[str], rows: list[tuple[str, tuple]] | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            for statement in statements:
                conn.execute(statement)
            for sql, params in rows or []:
                conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def _write_history_run(
        self,
        *,
        root_dir: Path,
        rel_base: str,
        run_name: str,
        summary_payload: dict,
        generated_at: str,
    ) -> Path:
        run_dir = root_dir / rel_base / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(
            json.dumps({**summary_payload, "metadata": {"generated_at": generated_at}}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (run_dir / "run-meta.json").write_text(
            json.dumps({"generated_at": generated_at, "run_name": run_name}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run_dir

    def _write_harness_run(
        self,
        *,
        run_name: str,
        summary_payload: dict,
        stage_payloads: dict[str, dict] | None = None,
        logs: dict[str, tuple[str, str]] | None = None,
    ) -> Path:
        run_dir = self.sandbox_root / "artifacts" / "harness-runs" / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for stage_name, payload in (stage_payloads or {}).items():
            (run_dir / f"{stage_name}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        for stage_name, content in (logs or {}).items():
            stdout_text, stderr_text = content
            (run_dir / f"{stage_name}.stdout.log").write_text(stdout_text, encoding="utf-8")
            (run_dir / f"{stage_name}.stderr.log").write_text(stderr_text, encoding="utf-8")
        return run_dir

    def _write_eval_run(
        self,
        *,
        run_name: str,
        summary_payload: dict,
    ) -> Path:
        run_dir = self.sandbox_root / "artifacts" / "harness-eval" / run_name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "summary.json").write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return run_dir

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

    def test_migrate_session_evidence_annotations_dry_run_and_apply(self):
        base = self._session_base_dirs()
        session_file = base / "sessions" / "dv-legacy-001.json"
        session_payload = {
            "session_id": "dv-legacy-001",
            "topic": "历史证据迁移",
            "updated_at": "2026-03-13T00:00:00Z",
            "interview_log": [
                {
                    "question": "当前最优先的阻塞是什么？",
                    "answer": "审批链条长导致整体处理慢",
                    "dimension": "customer_needs",
                    "options": ["审批链条长导致整体处理慢", "成本高", "资源不足"],
                    "is_follow_up": False,
                    "follow_up_round": 0,
                }
            ],
        }
        session_file.write_text(json.dumps(session_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        class FakeServer:
            @staticmethod
            def get_utc_now():
                return "2026-03-13T08:00:00Z"

            @staticmethod
            def backfill_session_interview_log_evidence_annotations(session, refresh_quality=True, overwrite_contract=False):
                log = session["interview_log"][0]
                log["answer_mode"] = "pick_with_reason"
                log["evidence_intent"] = "medium"
                log["answer_evidence_class"] = "rich_option"
                return {
                    "changed": True,
                    "logs_total": 1,
                    "logs_updated": 1,
                    "field_updates": {
                        "answer_mode": 1,
                        "evidence_intent": 1,
                        "answer_evidence_class": 1,
                    },
                }

        with patch.object(migrate_session_evidence_annotations, "get_script_dir", return_value=self.temp_scripts_dir):
            dry_run_summary = migrate_session_evidence_annotations.backfill_session_files(
                [session_file],
                apply_changes=False,
                server_module=FakeServer(),
            )
            self.assertEqual(1, dry_run_summary["sessions_changed"])
            dry_run_after = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertNotIn("answer_mode", dry_run_after["interview_log"][0])

            backup_dir = self.sandbox_root / "backup"
            backup_dir.mkdir(parents=True, exist_ok=True)
            apply_summary = migrate_session_evidence_annotations.backfill_session_files(
                [session_file],
                apply_changes=True,
                backup_dir=backup_dir,
                server_module=FakeServer(),
            )
            self.assertEqual(1, apply_summary["sessions_changed"])
            applied = json.loads(session_file.read_text(encoding="utf-8"))
            self.assertEqual("pick_with_reason", applied["interview_log"][0]["answer_mode"])
            self.assertEqual("medium", applied["interview_log"][0]["evidence_intent"])
            self.assertEqual("rich_option", applied["interview_log"][0]["answer_evidence_class"])
            self.assertTrue((backup_dir / "dv-legacy-001.json").exists())

    def test_replay_preflight_diagnostics_simulates_trigger_and_throttle(self):
        base = self._session_base_dirs()
        session_file = base / "sessions" / "dv-preflight-001.json"
        session_payload = {
            "session_id": "dv-preflight-001",
            "topic": "预检回放测试",
            "dimensions": {
                "customer_needs": {"coverage": 80, "items": []},
                "business_process": {"coverage": 40, "items": []},
            },
            "interview_log": [
                {
                    "dimension": "customer_needs",
                    "question": "最核心痛点是什么？",
                    "answer": "审批链条长导致整体处理慢",
                    "is_follow_up": False,
                },
                {
                    "dimension": "business_process",
                    "question": "角色分工里最容易卡在哪一段？",
                    "answer": "审批节点",
                    "is_follow_up": False,
                },
                {
                    "dimension": "business_process",
                    "question": "异常处理通常由谁兜底？",
                    "answer": "还没有固定角色",
                    "is_follow_up": False,
                },
            ],
        }
        session_file.write_text(json.dumps(session_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        class FakeServer:
            @staticmethod
            def build_session_evidence_ledger(session):
                logs = session.get("interview_log", [])
                if len(logs) <= 1:
                    return {"priority_dimensions": [], "dimensions": {"customer_needs": {"latest_probe_slots": []}}}
                if len(logs) == 2:
                    return {
                        "priority_dimensions": ["business_process"],
                        "dimensions": {
                            "business_process": {
                                "gap_score": 0.66,
                                "missing_aspects": ["角色分工"],
                                "latest_probe_slots": ["角色分工", "异常处理"],
                                "pending_follow_up_ratio": 0.5,
                                "evidence_density": 0.35,
                                "latest_needs_follow_up": True,
                                "latest_user_skip_follow_up": False,
                                "latest_signals": ["option_only"],
                            }
                        },
                        "shadow_draft": {"actions": {"ready": False, "blocking_dimensions": ["business_process"]}},
                        "formal_questions_total": len(logs),
                    }
                return {
                    "priority_dimensions": ["business_process"],
                    "dimensions": {
                        "business_process": {
                            "gap_score": 0.58,
                            "missing_aspects": ["角色分工"],
                            "latest_probe_slots": ["角色分工", "异常处理"],
                            "pending_follow_up_ratio": 0.45,
                            "evidence_density": 0.42,
                            "latest_needs_follow_up": True,
                            "latest_user_skip_follow_up": False,
                            "latest_signals": ["option_only"],
                        }
                    },
                    "shadow_draft": {"actions": {"ready": False, "blocking_dimensions": ["business_process"]}},
                    "formal_questions_total": len(logs),
                }

            @staticmethod
            def plan_mid_interview_preflight(session, dimension, ledger=None):
                logs = session.get("interview_log", [])
                if len(logs) == 2:
                    return {
                        "should_intervene": True,
                        "planner_mode": "gap_probe",
                        "reason": "角色分工证据不足",
                        "probe_slots": ["角色分工", "异常处理"],
                        "force_follow_up": False,
                        "fingerprint": "business_process::角色分工::角色分工|异常处理::actions",
                        "cooldown_suppressed": False,
                    }
                if len(logs) >= 3:
                    return {
                        "should_intervene": False,
                        "planner_mode": "observe",
                        "reason": "同类缺口刚刚追问过，先等待补答",
                        "probe_slots": ["角色分工", "异常处理"],
                        "force_follow_up": False,
                        "fingerprint": "business_process::角色分工::角色分工|异常处理::actions",
                        "cooldown_suppressed": True,
                        "cooldown_reason": "同类缺口刚刚追问过，先等待补答",
                    }
                return {
                    "should_intervene": False,
                    "planner_mode": "observe",
                    "reason": "",
                    "probe_slots": [],
                    "force_follow_up": False,
                    "fingerprint": "",
                    "cooldown_suppressed": False,
                }

        with patch.object(replay_preflight_diagnostics, "get_script_dir", return_value=self.temp_scripts_dir):
            summary = replay_preflight_diagnostics.simulate_session_files(
                [session_file],
                server_module=FakeServer(),
                max_events=5,
            )

        self.assertEqual(1, summary["sessions_total"])
        result = summary["results"][0]
        self.assertEqual("dv-preflight-001", result["session_id"])
        self.assertEqual(1, result["trigger_total"])
        self.assertEqual(1, result["throttled_total"])
        self.assertEqual("business_process", result["first_trigger"]["dimension"])

    def test_context_hub_prefers_local_binary(self):
        local_root = self.sandbox_root / "context-hub-local"
        local_bin = local_root / "node_modules" / ".bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        chub_path = local_bin / "chub"
        chub_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        resolved = context_hub.resolve_command(
            "chub",
            root_dir=local_root,
            which=lambda _: None,
        )

        self.assertEqual("local-node_modules", resolved.source)
        self.assertEqual((str(chub_path),), resolved.command)

    def test_context_hub_falls_back_to_npx_when_missing(self):
        resolved = context_hub.resolve_command(
            "chub",
            root_dir=self.sandbox_root / "context-hub-npx",
            which=lambda name: "/usr/bin/npx" if name == "npx" else None,
        )

        self.assertEqual("npx-package", resolved.source)
        self.assertEqual(
            ("/usr/bin/npx", "--yes", "--package", "@aisuite/chub", "--", "chub"),
            resolved.command,
        )

    def test_context_hub_doctor_reports_runtime(self):
        payload = context_hub.build_doctor_payload(
            root_dir=self.sandbox_root / "context-hub-doctor",
            which=lambda name: {
                "node": "/usr/bin/node",
                "npm": "/usr/bin/npm",
                "npx": "/usr/bin/npx",
            }.get(name),
        )

        self.assertEqual("@aisuite/chub", payload["package_name"])
        self.assertEqual("/usr/bin/node", payload["runtime"]["node"])
        self.assertEqual("npx-package", payload["tools"]["chub"]["source"])
        self.assertEqual("npx-package", payload["tools"]["chub-mcp"]["source"])

    def test_agent_doctor_collects_failures_for_placeholder_cloud_env(self):
        env_file = self.sandbox_root / "agent-doctor-cloud.env"
        env_file.write_text(
            "\n".join(
                [
                    "DEBUG_MODE=false",
                    "SMS_PROVIDER=mock",
                    "SECRET_KEY=replace-with-a-strong-random-secret",
                    "INSTANCE_SCOPE_KEY=replace-with-instance-scope-key",
                    "WECHAT_LOGIN_ENABLED=true",
                    *self._agent_doctor_env_lines("agent-doctor-cloud"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        file_values, effective_env = agent_doctor.build_effective_env(env_file, {})
        results = agent_doctor.collect_checks(
            profile="cloud",
            selected_env_file=env_file,
            env_source="test",
            file_values=file_values,
            effective_env=effective_env,
        )

        by_name = {item.name: item for item in results}
        self.assertEqual("FAIL", by_name["SECRET_KEY"].status)
        self.assertEqual("FAIL", by_name["INSTANCE_SCOPE_KEY"].status)
        self.assertEqual("FAIL", by_name["SMS_PROVIDER"].status)
        self.assertEqual("FAIL", by_name["微信登录"].status)

    def test_agent_doctor_accepts_local_env_with_mock_sms_and_custom_secret(self):
        env_file = self.sandbox_root / "agent-doctor-local.env"
        env_file.write_text(
            "\n".join(
                [
                    "DEBUG_MODE=true",
                    "SMS_PROVIDER=mock",
                    "SECRET_KEY=local-dev-secret",
                    "INSTANCE_SCOPE_KEY=deepvision-local",
                    *self._agent_doctor_env_lines("agent-doctor-local"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        file_values, effective_env = agent_doctor.build_effective_env(env_file, {})
        with patch("scripts.agent_doctor.shutil.which") as mock_which:
            mock_which.side_effect = lambda name: {
                "python3": "/usr/bin/python3",
                "uv": "/usr/bin/uv",
            }.get(name)
            results = agent_doctor.collect_checks(
                profile="local",
                selected_env_file=env_file,
                env_source="test",
                file_values=file_values,
                effective_env=effective_env,
            )
        summary = agent_doctor.build_summary(results)
        self.assertEqual(0, summary["FAIL"])
        by_name = {item.name: item for item in results}
        self.assertIn(by_name["SMS_PROVIDER"].status, {"WARN", "PASS"})
        self.assertEqual("PASS", by_name["SECRET_KEY"].status)
        self.assertEqual("PASS", by_name["INSTANCE_SCOPE_KEY"].status)

    def test_agent_doctor_accepts_disabled_sms_login_in_cloud_env(self):
        env_file = self.sandbox_root / "agent-doctor-cloud-sms-disabled.env"
        env_file.write_text(
            "\n".join(
                [
                    "DEBUG_MODE=false",
                    "SMS_LOGIN_ENABLED=false",
                    "SMS_PROVIDER=mock",
                    "SECRET_KEY=cloud-secret",
                    "INSTANCE_SCOPE_KEY=deepvision-cloud",
                    *self._agent_doctor_env_lines("agent-doctor-cloud-sms-disabled"),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        file_values, effective_env = agent_doctor.build_effective_env(env_file, {})
        results = agent_doctor.collect_checks(
            profile="cloud",
            selected_env_file=env_file,
            env_source="test",
            file_values=file_values,
            effective_env=effective_env,
        )

        by_name = {item.name: item for item in results}
        self.assertEqual("PASS", by_name["短信登录"].status)
        self.assertEqual("PASS", by_name["SMS_PROVIDER"].status)

    def test_agent_smoke_suite_definitions_cover_core_flow(self):
        minimal_cases = agent_smoke.resolve_suite_cases("minimal")
        minimal_ids = [item.test_id for item in minimal_cases]
        self.assertIn(
            "tests.test_api_comprehensive.ComprehensiveApiTests.test_auth_lifecycle",
            minimal_ids,
        )
        self.assertIn(
            "tests.test_api_comprehensive.ComprehensiveApiTests.test_standard_user_can_generate_balanced_but_cannot_access_solution_appendix_or_presentation",
            minimal_ids,
        )
        self.assertIn(
            "tests.test_security_regression.SecurityRegressionTests.test_anonymous_write_endpoints_are_blocked",
            minimal_ids,
        )

        extended_cases = agent_smoke.resolve_suite_cases("extended")
        self.assertGreater(len(extended_cases), len(minimal_cases))

    def test_agent_browser_smoke_suite_definitions_cover_ui_flow(self):
        scenarios = agent_browser_smoke.resolve_suite_scenarios("minimal")
        scenario_ids = [item.scenario_id for item in scenarios]
        self.assertEqual(
            ["help-docs", "solution-share", "admin-config-entry"],
            scenario_ids,
        )

        extended_scenarios = agent_browser_smoke.resolve_suite_scenarios("extended")
        extended_ids = [item.scenario_id for item in extended_scenarios]
        self.assertEqual(
            [
                "help-docs",
                "solution-share",
                "admin-config-entry",
                "solution-public-readonly",
                "solution-public-readonly-refresh",
                "login-view",
                "login-sms-only-view",
                "login-wechat-only-view",
                "license-gate-view",
                "license-activate-success",
                "license-activate-refresh",
                "report-detail-flow",
                "report-detail-refresh",
                "interview-refresh",
                "report-generation-refresh",
                "admin-config-tab",
            ],
            extended_ids,
        )

        live_scenarios = agent_browser_smoke.resolve_suite_scenarios("live-minimal")
        live_ids = [item.scenario_id for item in live_scenarios]
        self.assertEqual(["live-login-license-flow"], live_ids)
        live_extended_scenarios = agent_browser_smoke.resolve_suite_scenarios("live-extended")
        live_extended_ids = [item.scenario_id for item in live_extended_scenarios]
        self.assertEqual(
            [
                "live-login-license-flow",
                "live-report-generation-refresh",
                "live-report-solution-flow",
                "live-solution-public-share-flow",
            ],
            live_extended_ids,
        )

    def test_agent_guardrails_suite_definitions_cover_core_invariants(self):
        minimal_cases = agent_guardrails.resolve_suite_cases("minimal")
        minimal_ids = [item.test_id for item in minimal_cases]
        self.assertIn(
            "tests.test_security_regression.SecurityRegressionTests.test_anonymous_write_endpoints_are_blocked",
            minimal_ids,
        )
        self.assertIn(
            "tests.test_security_regression.SecurityRegressionTests.test_license_gate_blocks_business_routes_but_allows_auth_and_license_endpoints",
            minimal_ids,
        )
        self.assertIn(
            "tests.test_api_comprehensive.ComprehensiveApiTests.test_admin_ownership_migration_endpoints_cover_search_preview_apply_and_rollback",
            minimal_ids,
        )

        extended_cases = agent_guardrails.resolve_suite_cases("extended")
        self.assertGreater(len(extended_cases), len(minimal_cases))

    def test_agent_profiles_load_expected_tasks(self):
        task_names = agent_profiles.list_task_names()
        self.assertIn("account-merge", task_names)
        self.assertIn("license-admin", task_names)
        self.assertIn("license-audit", task_names)
        self.assertIn("ownership-migration", task_names)
        self.assertIn("cloud-import", task_names)
        self.assertIn("config-center", task_names)
        self.assertIn("presentation-export", task_names)
        self.assertIn("report-solution", task_names)

        profile = agent_profiles.get_task_profile("ownership-migration")
        self.assertEqual("high", profile["risk_level"])
        self.assertEqual("extended", profile["guardrails_suite"])
        self.assertEqual("ownership-migration", profile["contract"])
        self.assertTrue(profile["workflow"]["steps"])

    def test_agent_contracts_load_expected_high_risk_contracts(self):
        contracts = agent_contracts.load_contracts()
        self.assertIn("license-admin", contracts)
        self.assertIn("ownership-migration", contracts)
        self.assertIn("done_when", contracts["license-admin"])
        self.assertIn("evidence_required", contracts["ownership-migration"])
        self.assertTrue(contracts["license-admin"]["source_file"].endswith("resources/harness/contracts/license-admin.json"))

    def test_agent_calibration_loads_report_solution_wording_sample(self):
        samples = agent_calibration.load_calibration_samples()
        sample_names = {item["name"] for item in samples}
        self.assertIn("report-solution-wording-drift", sample_names)
        self.assertIn("tenant-leak-must-fail", sample_names)
        self.assertIn("share-readonly-regression-must-fail", sample_names)
        self.assertIn("license-gate-ui-wording-drift-should-warn", sample_names)
        self.assertIn("workflow-governance-missing-must-fail", sample_names)
        self.assertIn("presentation-sidecar-integrity-must-fail", sample_names)
        self.assertGreaterEqual(len(samples), 6)
        target = next(item for item in samples if item["name"] == "report-solution-wording-drift")
        self.assertEqual("WARN", target["expected_decision"])
        self.assertIn("report-solution-preview", target["applies_to"]["scenarios"])
        self.assertTrue(target["source_file"].endswith("tests/harness_calibration/report-solution-wording-drift.json"))

    def test_agent_eval_loads_expected_repo_scenarios(self):
        scenarios = agent_eval.load_scenarios()
        scenario_names = {item.name for item in scenarios}
        self.assertIn("browser-smoke-minimal", scenario_names)
        self.assertIn("browser-smoke-extended", scenario_names)
        self.assertIn("browser-smoke-live-minimal", scenario_names)
        self.assertIn("browser-smoke-live-extended", scenario_names)
        self.assertIn("instance-scope-boundaries", scenario_names)
        self.assertIn("asset-ownership-boundaries", scenario_names)
        self.assertIn("account-merge-rollback", scenario_names)
        self.assertIn("ownership-migration-core", scenario_names)
        self.assertIn("license-admin-preview", scenario_names)
        self.assertIn("report-solution-core", scenario_names)
        self.assertIn("report-solution-preview", scenario_names)
        self.assertIn("ownership-migration-governance", scenario_names)
        self.assertIn("access-boundaries", scenario_names)
        self.assertIn("presentation-map-concurrency", scenario_names)
        self.assertIn("observability-and-config", scenario_names)
        self.assertIn("env-overlay-resolution", scenario_names)
        self.assertIn("runtime-readiness", scenario_names)

        target = next(item for item in scenarios if item.name == "runtime-readiness")
        self.assertEqual("ops", target.category)
        self.assertIn("nightly", target.tags)
        self.assertEqual("unittest", target.executor)
        self.assertTrue(
            any(
                case.test_id == "tests.test_api_comprehensive.ComprehensiveApiTests.test_runtime_startup_snapshot_persists_to_store_and_file"
                for case in target.cases
            )
        )
        browser_target = next(item for item in scenarios if item.name == "browser-smoke-minimal")
        self.assertEqual("browser_smoke", browser_target.executor)
        self.assertEqual("minimal", browser_target.executor_config["suite"])
        extended_browser_target = next(item for item in scenarios if item.name == "browser-smoke-extended")
        self.assertEqual("browser_smoke", extended_browser_target.executor)
        self.assertEqual("extended", extended_browser_target.executor_config["suite"])
        self.assertIn("stability-local", extended_browser_target.tags)
        self.assertIn("stability-local-core", extended_browser_target.tags)
        live_browser_target = next(item for item in scenarios if item.name == "browser-smoke-live-minimal")
        self.assertEqual("browser_smoke", live_browser_target.executor)
        self.assertEqual("live-minimal", live_browser_target.executor_config["suite"])
        self.assertIn("stability-local-release", live_browser_target.tags)
        live_extended_browser_target = next(item for item in scenarios if item.name == "browser-smoke-live-extended")
        self.assertEqual("browser_smoke", live_extended_browser_target.executor)
        self.assertEqual("live-extended", live_extended_browser_target.executor_config["suite"])
        workflow_target = next(item for item in scenarios if item.name == "report-solution-preview")
        self.assertEqual("workflow", workflow_target.executor)
        self.assertEqual("report-solution", workflow_target.executor_config["task"])
        self.assertIsNotNone(workflow_target.plan)
        self.assertEqual("report-solution", workflow_target.plan["task"])
        self.assertTrue(any(sample["name"] == "report-solution-wording-drift" for sample in workflow_target.calibration_samples))
        browser_extended_target = next(item for item in scenarios if item.name == "browser-smoke-extended")
        self.assertTrue(any(sample["name"] == "license-gate-ui-wording-drift-should-warn" for sample in browser_extended_target.calibration_samples))
        license_admin_target = next(item for item in scenarios if item.name == "license-admin-preview")
        self.assertEqual("workflow", license_admin_target.executor)
        self.assertEqual("license-admin", license_admin_target.executor_config["task"])
        self.assertIsNotNone(license_admin_target.contract)
        self.assertEqual("license-admin", license_admin_target.contract["name"])
        self.assertIsNotNone(license_admin_target.plan)
        self.assertEqual("license-admin", license_admin_target.plan["task"])
        self.assertTrue(any(sample["name"] == "workflow-governance-missing-must-fail" for sample in license_admin_target.calibration_samples))
        governance_target = next(item for item in scenarios if item.name == "ownership-migration-governance")
        self.assertIsNotNone(governance_target.contract)
        self.assertEqual("ownership-migration", governance_target.contract["name"])
        self.assertTrue(any(sample["name"] == "workflow-governance-missing-must-fail" for sample in governance_target.calibration_samples))
        env_target = next(item for item in scenarios if item.name == "env-overlay-resolution")
        self.assertEqual("ops", env_target.category)
        self.assertTrue(
            any(
                case.test_id == "tests.test_runtime_token_config.RuntimeTokenConfigTests.test_explicit_env_file_supports_base_and_overlay"
                for case in env_target.cases
            )
        )
        stability_targets = agent_eval.filter_scenarios(scenarios, tags=["stability-local"])
        stability_names = {item.name for item in stability_targets}
        self.assertIn("stability-failure-degrade", stability_names)
        self.assertIn("stability-idempotency", stability_names)
        self.assertIn("browser-smoke-extended", stability_names)
        self.assertIn("report-solution-core", stability_names)
        self.assertIn("access-boundaries", stability_names)
        self.assertIn("asset-ownership-boundaries", stability_names)
        self.assertNotIn("browser-smoke-live-minimal", stability_names)
        tenant_target = next(item for item in scenarios if item.name == "instance-scope-boundaries")
        self.assertTrue(any(sample["name"] == "tenant-leak-must-fail" for sample in tenant_target.calibration_samples))
        asset_target = next(item for item in scenarios if item.name == "asset-ownership-boundaries")
        self.assertTrue(any(sample["name"] == "share-readonly-regression-must-fail" for sample in asset_target.calibration_samples))
        access_target = next(item for item in scenarios if item.name == "access-boundaries")
        self.assertTrue(any(sample["name"] == "share-readonly-regression-must-fail" for sample in access_target.calibration_samples))
        presentation_target = next(item for item in scenarios if item.name == "presentation-map-concurrency")
        self.assertTrue(any(sample["name"] == "presentation-sidecar-integrity-must-fail" for sample in presentation_target.calibration_samples))
        presentation_target = next(item for item in scenarios if item.name == "presentation-map-concurrency")
        self.assertEqual("security", presentation_target.category)
        self.assertTrue(
            any(
                case.test_id == "tests.test_security_regression.SecurityRegressionTests.test_presentation_map_remains_valid_under_parallel_updates"
                for case in presentation_target.cases
            )
        )
        tenant_target = next(item for item in scenarios if item.name == "instance-scope-boundaries")
        self.assertEqual("tenant", tenant_target.category)
        self.assertIn("nightly", tenant_target.tags)
        self.assertTrue(
            any(
                case.test_id == "tests.test_api_comprehensive.ComprehensiveApiTests.test_report_isolation_between_instance_scopes_for_same_user"
                for case in tenant_target.cases
            )
        )
        asset_tenant_target = next(item for item in scenarios if item.name == "asset-ownership-boundaries")
        self.assertEqual("tenant", asset_tenant_target.category)
        self.assertIn("manual", asset_tenant_target.tags)
        self.assertTrue(
            any(
                case.test_id == "tests.test_security_regression.SecurityRegressionTests.test_report_solution_share_link_requires_owner_and_allows_public_readonly_access"
                for case in asset_tenant_target.cases
            )
        )

    def test_agent_scenario_scaffold_builds_from_eval_run(self):
        run_dir = self._write_eval_run(
            run_name="eval-run",
            summary_payload={
                "overall": "BLOCKED",
                "results": [
                    {
                        "name": "access-boundaries",
                        "category": "security",
                        "status": "FAIL",
                        "detail": "attempts=1 pass=0 fail=1 max_ms=1200",
                        "stats": {
                            "attempts": 1,
                            "max_duration_ms": 1200,
                            "max_duration_budget_ms": 150000,
                            "budget_exceeded": False,
                        },
                        "cases": [
                            {
                                "test_id": "tests.test_security_regression.SecurityRegressionTests.test_anonymous_write_endpoints_are_blocked",
                                "label": "匿名写接口拦截",
                            },
                            {
                                "test_id": "tests.test_security_regression.SecurityRegressionTests.test_report_solution_share_link_requires_owner_and_allows_public_readonly_access",
                                "label": "方案页分享只读边界",
                            },
                        ],
                    }
                ],
            },
        )
        payload, context = agent_scenario_scaffold.scaffold_scenario(
            source="eval",
            run_dir=str(run_dir),
        )
        self.assertEqual("security", context["category"])
        self.assertEqual(2, context["cases_count"])
        self.assertIn("incident", payload["tags"])
        self.assertEqual("security", payload["category"])
        self.assertTrue(payload["description"])
        self.assertEqual("security", context["suggested_category"])
        self.assertIn("security", context["suggested_tags"])
        self.assertEqual(150000, context["suggested_budget_ms"])
        self.assertTrue(context["suggested_output_path"].startswith("tests/harness_scenarios/security/"))
        self.assertIn("--category security", context["scaffold_commands"]["write"])
        self.assertIn("--tag security", context["scaffold_commands"]["write"])
        self.assertIn("--budget-ms 150000", context["scaffold_commands"]["write"])

    def test_agent_scenario_scaffold_builds_executor_template_from_eval_browser_run(self):
        run_dir = self._write_eval_run(
            run_name="eval-browser-run",
            summary_payload={
                "overall": "BLOCKED",
                "results": [
                    {
                        "name": "browser-smoke-extended",
                        "category": "browser",
                        "status": "FAIL",
                        "detail": "attempts=1 pass=0 fail=1 suite=extended max_ms=2100",
                        "tags": ["nightly", "browser", "ui"],
                        "executor": "browser_smoke",
                        "executor_config": {
                            "type": "browser_smoke",
                            "suite": "extended",
                            "allowed_overalls": ["READY"],
                        },
                        "stats": {
                            "attempts": 1,
                            "max_duration_ms": 2100,
                            "max_duration_budget_ms": 240000,
                            "budget_exceeded": False,
                        },
                    }
                ],
            },
        )
        payload, context = agent_scenario_scaffold.scaffold_scenario(
            source="eval",
            run_dir=str(run_dir),
        )
        self.assertEqual("browser", payload["category"])
        self.assertEqual("browser_smoke", payload["executor"]["type"])
        self.assertEqual("extended", payload["executor"]["suite"])
        self.assertEqual(0, context["cases_count"])
        self.assertIn("browser", payload["tags"])
        self.assertIn("ui", payload["tags"])
        self.assertNotIn("nightly", payload["tags"])
        self.assertEqual(240000, context["suggested_budget_ms"])
        self.assertIn("--tag browser", context["scaffold_commands"]["write"])
        self.assertIn("--tag ui", context["scaffold_commands"]["write"])
        self.assertIn("--output tests/harness_scenarios/browser/", context["scaffold_commands"]["write"])

    def test_agent_scenario_scaffold_builds_from_harness_run_logs(self):
        run_dir = self._write_harness_run(
            run_name="harness-run",
            summary_payload={
                "overall": "BLOCKED",
                "task": {"name": "report-solution"},
                "results": [
                    {"name": "smoke", "status": "FAIL", "detail": "suite=minimal cases=2"},
                ],
            },
            stage_payloads={
                "smoke": {
                    "cases": [
                        {
                            "test_id": "tests.test_api_comprehensive.ComprehensiveApiTests.test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints",
                            "label": "专业版方案页与分享能力",
                        },
                        {
                            "test_id": "tests.test_solution_payload.SolutionPayloadTests.test_build_solution_payload_falls_back_to_legacy_markdown_for_old_report",
                            "label": "方案页旧报告兼容",
                        },
                    ]
                }
            },
            logs={
                "smoke": (
                    "FAIL: test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints (tests.test_api_comprehensive.ComprehensiveApiTests.test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints)\n",
                    "",
                )
            },
        )
        payload, context = agent_scenario_scaffold.scaffold_scenario(
            source="harness",
            run_dir=str(run_dir),
        )
        self.assertEqual("report-solution", context["category"])
        self.assertEqual(1, context["cases_count"])
        self.assertEqual(
            "tests.test_api_comprehensive.ComprehensiveApiTests.test_professional_user_can_access_solution_share_appendix_and_presentation_endpoints",
            payload["cases"][0]["test_id"],
        )
        self.assertEqual("report-solution", context["suggested_category"])
        self.assertIn("--category report-solution", context["scaffold_commands"]["write"])
        self.assertIn("--tag report", context["scaffold_commands"]["write"])

    def test_agent_scenario_scaffold_builds_workflow_template_from_harness_run(self):
        run_dir = self._write_harness_run(
            run_name="harness-workflow-run",
            summary_payload={
                "overall": "BLOCKED",
                "task": {"name": "license-admin"},
                "results": [
                    {"name": "workflow", "status": "FAIL", "detail": "task=license-admin risk=high execute=preview"},
                ],
            },
            stage_payloads={
                "workflow": {
                    "command": "python3 scripts/agent_workflow.py --task license-admin --execute preview",
                    "workflow": {
                        "overall": "BLOCKED",
                        "workflow": {
                            "risk_level": "high",
                            "workflow_mode": "verify_first",
                            "steps": [],
                            "hidden_apply_steps": [],
                        },
                    },
                }
            },
        )
        payload, context = agent_scenario_scaffold.scaffold_scenario(
            source="harness",
            run_dir=str(run_dir),
        )
        self.assertEqual("ops", payload["category"])
        self.assertEqual("workflow", payload["executor"]["type"])
        self.assertEqual("license-admin", payload["executor"]["task"])
        self.assertEqual("preview", payload["executor"]["execute_mode"])
        self.assertEqual(0, context["cases_count"])
        self.assertIn("workflow", payload["tags"])
        self.assertIn("--tag workflow", context["scaffold_commands"]["write"])
        self.assertIn("--category ops", context["scaffold_commands"]["write"])

    def test_agent_scenario_scaffold_can_write_output_file(self):
        run_dir = self._write_eval_run(
            run_name="eval-run-write",
            summary_payload={
                "overall": "BLOCKED",
                "results": [
                    {
                        "name": "runtime-readiness",
                        "category": "ops",
                        "status": "FAIL",
                        "detail": "attempts=1 pass=0 fail=1 max_ms=900",
                        "stats": {
                            "attempts": 1,
                            "max_duration_ms": 900,
                            "max_duration_budget_ms": 120000,
                            "budget_exceeded": False,
                        },
                        "cases": [
                            {
                                "test_id": "tests.test_scripts_comprehensive.ComprehensiveScriptTests.test_agent_doctor_collects_failures_for_placeholder_cloud_env",
                                "label": "cloud doctor 风险识别",
                            }
                        ],
                    }
                ],
            },
        )
        output_file = self.sandbox_root / "scenario-output.json"
        exit_code = agent_scenario_scaffold.main(
            [
                "--source",
                "eval",
                "--run-dir",
                str(run_dir),
                "--output",
                str(output_file),
            ]
        )
        self.assertEqual(0, exit_code)
        written = json.loads(output_file.read_text(encoding="utf-8"))
        self.assertEqual("ops", written["category"])
        self.assertEqual(1, len(written["cases"]))

    def test_agent_eval_reports_flaky_scenarios_and_writes_artifacts(self):
        scenario_root = self.sandbox_root / "eval-scenarios"
        scenario_dir = scenario_root / "workflow"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "report-solution-preview.json").write_text(
            json.dumps(
                {
                    "name": "report-solution-preview",
                    "category": "workflow",
                    "description": "验证 evaluator 聚合输出与校准样本引用",
                    "tags": ["nightly", "report", "workflow"],
                    "budgets": {"max_duration_ms": 5000},
                    "cases": [
                        {
                            "test_id": "tests.fake.Class.test_case",
                            "label": "假用例",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        fake_attempts = [
            agent_eval.SuiteExecution(
                command=["python3", "-m", "unittest", "tests.fake.Class.test_case"],
                returncode=2,
                stdout="",
                stderr="FAIL: test_case (tests.fake.Class.test_case)\nAssertionError: boom\n",
            ),
            agent_eval.SuiteExecution(
                command=["python3", "-m", "unittest", "tests.fake.Class.test_case"],
                returncode=0,
                stdout=".\nOK\n",
                stderr="",
            ),
        ]

        with patch.object(agent_eval, "run_suite_process", side_effect=fake_attempts):
            payload, artifact_paths, exit_code = agent_eval.run_eval(
                scenarios_root=scenario_root,
                tags=["nightly"],
                repeat=2,
                artifact_dir=str(self.sandbox_root / "eval-artifacts"),
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("DEGRADED", payload["overall"])
        self.assertEqual(1, payload["summary"]["FLAKY"])
        self.assertEqual("report-solution-preview", payload["results"][0]["name"])
        self.assertTrue(payload["results"][0]["calibration_samples"])
        self.assertTrue(
            any(sample["name"] == "report-solution-wording-drift" for sample in payload["results"][0]["calibration_samples"])
        )
        self.assertEqual("tests.fake.Class.test_case", payload["failure_hotspots"][0]["test_id"])
        self.assertIsNotNone(artifact_paths)
        self.assertTrue(Path(artifact_paths["run_dir"]).exists())
        self.assertTrue((Path(artifact_paths["run_dir"]) / "report-solution-preview.json").exists())
        self.assertTrue((Path(artifact_paths["run_dir"]) / "progress.md").exists())
        self.assertTrue((Path(artifact_paths["run_dir"]) / "failure-summary.md").exists())
        self.assertTrue((Path(artifact_paths["run_dir"]) / "handoff.json").exists())
        self.assertTrue((Path(artifact_paths["base_dir"]) / "latest-progress.md").exists())
        self.assertTrue((Path(artifact_paths["base_dir"]) / "latest-failure-summary.md").exists())
        self.assertTrue((Path(artifact_paths["base_dir"]) / "latest-handoff.json").exists())
        progress_md = (Path(artifact_paths["run_dir"]) / "progress.md").read_text(encoding="utf-8")
        self.assertIn("Evaluator Progress", progress_md)
        self.assertIn("`workflow/report-solution-preview`: FLAKY", progress_md)
        self.assertIn("calibration=1", progress_md)
        failure_summary_md = (Path(artifact_paths["run_dir"]) / "failure-summary.md").read_text(encoding="utf-8")
        self.assertIn("Evaluator Failure Summary", failure_summary_md)
        self.assertIn("tests.fake.Class.test_case", failure_summary_md)
        self.assertIn("方案页文案漂移应按语义校验，不按逐字文案误判", failure_summary_md)
        self.assertIn("python3 scripts/agent_scenario_scaffold.py --source eval --run-dir", failure_summary_md)
        self.assertIn("--category workflow", failure_summary_md)
        self.assertIn("--tag incident", failure_summary_md)
        self.assertIn("--output tests/harness_scenarios/workflow/", failure_summary_md)
        handoff_payload = json.loads((Path(artifact_paths["run_dir"]) / "handoff.json").read_text(encoding="utf-8"))
        self.assertEqual("evaluator", handoff_payload["kind"])
        self.assertTrue(any("report-solution-preview" in item for item in handoff_payload["todo"]))
        self.assertIn("python3 scripts/agent_eval.py --scenario report-solution-preview --repeat 2", handoff_payload["resume_commands"])
        self.assertTrue(any("tests/harness_calibration/report-solution-wording-drift.json" == item for item in handoff_payload["docs"]))
        self.assertEqual("report-solution-wording-drift", handoff_payload["calibration_samples"][0]["name"])
        self.assertTrue(
            any(
                item.startswith("python3 scripts/agent_scenario_scaffold.py --source eval --run-dir ")
                for item in handoff_payload["resume_commands"]
            )
        )
        self.assertEqual("workflow", handoff_payload["scaffold_recommendation"]["category"])
        self.assertEqual(5000, handoff_payload["scaffold_recommendation"]["budget_ms"])
        latest_payload = json.loads((Path(artifact_paths["base_dir"]) / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(str(Path(artifact_paths["run_dir"]) / "handoff.json"), latest_payload["handoff_file"])

    def test_agent_playbook_sync_check_passes_for_repo(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = agent_playbook_sync.main(["--check"])
        self.assertEqual(0, exit_code)
        self.assertIn("task-backed playbook 均已同步", stdout.getvalue())

    def test_agent_workflow_attaches_contract_for_high_risk_profile(self):
        workflow_root = self.sandbox_root / "workflow-contract-license-admin"
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / ".env.local").write_text("ADMIN_PHONE_NUMBERS=13900000000\n", encoding="utf-8")
        profile = agent_profiles.get_task_profile("license-admin")

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={},
            allow_apply=False,
            execute_mode="plan",
            root_dir=workflow_root,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("license-admin", payload["contract"]["name"])
        self.assertIn("done_when", payload["contract"])
        self.assertTrue(payload["contract"]["source_file"].endswith("resources/harness/contracts/license-admin.json"))
        self.assertEqual("license-admin", payload["plan"]["task"])
        self.assertIn("python3 scripts/agent_planner.py --task license-admin", payload["plan"]["generate_command"])

    def test_agent_missions_load_expected_task_mission(self):
        mission = agent_missions.get_mission("ownership-migration")
        self.assertIsNotNone(mission)
        self.assertEqual("ownership-migration", mission["task"])
        self.assertIn("python3 scripts/agent_planner.py --task ownership-migration", mission["generate_command"])

    def test_agent_workflow_attaches_mission_for_profile(self):
        profile = agent_profiles.get_task_profile("report-solution")

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={},
            allow_apply=False,
            execute_mode="plan",
            root_dir=self.sandbox_root / "workflow-report-solution",
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("report-solution", payload["mission"]["task"])
        self.assertIn("Mission Contract", payload["mission"]["title"])

    def test_agent_planner_writes_markdown_and_json_artifacts(self):
        planner_dir = self.sandbox_root / "planner-output"
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            exit_code = agent_planner.main(
                [
                    "--task",
                    "report-solution",
                    "--goal",
                    "修复方案页分享异常并保留旧报告兼容",
                    "--context-line",
                    "用户反馈公开分享页偶发空白",
                    "--context-line",
                    "需要先确认是 payload 回退还是分享边界问题",
                    "--plan-name",
                    "report-solution-share-fix",
                    "--artifact-dir",
                    str(planner_dir),
                ]
            )

        self.assertEqual(0, exit_code)
        mission_markdown_path = planner_dir / "report-solution-share-fix.mission.md"
        mission_json_path = planner_dir / "report-solution-share-fix.mission.json"
        markdown_path = planner_dir / "report-solution-share-fix.md"
        json_path = planner_dir / "report-solution-share-fix.json"
        mission_pointer_path = ROOT_DIR / "artifacts" / "planner" / "missions" / "by-task" / "report-solution" / "latest.json"
        pointer_path = ROOT_DIR / "artifacts" / "planner" / "by-task" / "report-solution" / "latest.json"
        self.assertTrue(mission_markdown_path.exists())
        self.assertTrue(mission_json_path.exists())
        self.assertTrue(markdown_path.exists())
        self.assertTrue(json_path.exists())
        self.assertTrue(mission_pointer_path.exists())
        self.assertTrue(pointer_path.exists())
        mission_markdown = mission_markdown_path.read_text(encoding="utf-8")
        mission_payload = json.loads(mission_json_path.read_text(encoding="utf-8"))
        mission_pointer = json.loads(mission_pointer_path.read_text(encoding="utf-8"))
        markdown = markdown_path.read_text(encoding="utf-8")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        self.assertIn("Mission Contract", mission_markdown)
        self.assertEqual("mission", mission_payload["kind"])
        self.assertEqual("report-solution", mission_payload["task"])
        self.assertEqual(str(mission_markdown_path.resolve()), mission_pointer["markdown_file"])
        self.assertIn("Planner Artifact", markdown)
        self.assertIn("修复方案页分享异常并保留旧报告兼容", markdown)
        self.assertIn("上游 Mission", markdown)
        self.assertIn("方案页继续消费已绑定报告的最终快照", markdown)
        self.assertEqual("planner", payload["kind"])
        self.assertEqual("report-solution", payload["task"])
        self.assertEqual("report-solution", pointer["task"])
        self.assertEqual(str(markdown_path.resolve()), pointer["markdown_file"])
        self.assertEqual(str(json_path.resolve()), pointer["json_file"])
        self.assertEqual("report-solution", payload["mission"]["task"])
        self.assertIn("公开分享保持匿名只读", "\n".join(payload["acceptance_focus"]))
        self.assertIn("[WRITE]", stdout.getvalue())

    def test_agent_heartbeat_writes_markdown_and_json_artifacts(self):
        sandbox_root = self.sandbox_root / "heartbeat-root"
        progress_dir = sandbox_root / "docs" / "agent"
        progress_dir.mkdir(parents=True, exist_ok=True)
        (progress_dir / "harness-progress-phase5.md").write_text(
            "\n".join(
                [
                    "# progress",
                    "",
                    "- 当前阶段：`active`",
                    "- 当前优先项：`H5-3 Global Heartbeat Memory`",
                    "- 对应计划：[harness-iteration-plan-phase5.md](docs/agent/harness-iteration-plan-phase5.md)",
                    "",
                    "| 日期 | 编号 | 状态 | 事项 | 证据 | 下一步 |",
                    "| --- | --- | --- | --- | --- | --- |",
                    "| 2026-04-10 | H5-2 | done | 已完成 mission | x | 启动 H5-3 |",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (progress_dir / "harness-iteration-plan-phase5.md").write_text("# plan\n", encoding="utf-8")
        mission_pointer = sandbox_root / "artifacts" / "planner" / "missions" / "by-task" / "report-solution" / "latest.json"
        mission_pointer.parent.mkdir(parents=True, exist_ok=True)
        mission_pointer.write_text(
            json.dumps(
                {
                    "task": "report-solution",
                    "mission_name": "report-solution-share-fix-mission",
                    "goal": "修复方案页分享异常",
                    "generated_at": "2026-04-10T00:00:00Z",
                    "markdown_file": str((sandbox_root / "artifacts" / "planner" / "report-solution-share-fix.mission.md").resolve()),
                    "json_file": str((sandbox_root / "artifacts" / "planner" / "report-solution-share-fix.mission.json").resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan_pointer = sandbox_root / "artifacts" / "planner" / "by-task" / "report-solution" / "latest.json"
        plan_pointer.parent.mkdir(parents=True, exist_ok=True)
        plan_pointer.write_text(
            json.dumps(
                {
                    "task": "report-solution",
                    "plan_name": "report-solution-share-fix",
                    "goal": "修复方案页分享异常",
                    "generated_at": "2026-04-10T00:00:00Z",
                    "markdown_file": str((sandbox_root / "artifacts" / "planner" / "report-solution-share-fix.md").resolve()),
                    "json_file": str((sandbox_root / "artifacts" / "planner" / "report-solution-share-fix.json").resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        harness_latest = sandbox_root / "artifacts" / "harness-runs" / "latest.json"
        harness_latest.parent.mkdir(parents=True, exist_ok=True)
        harness_latest.write_text(
            json.dumps(
                {
                    "overall": "READY",
                    "metadata": {"generated_at": "2026-04-10T00:00:00Z"},
                    "handoff_file": str((sandbox_root / "artifacts" / "harness-runs" / "latest-handoff.json").resolve()),
                    "progress_file": str((sandbox_root / "artifacts" / "harness-runs" / "latest-progress.md").resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        evaluator_latest = sandbox_root / "artifacts" / "harness-eval" / "latest.json"
        evaluator_latest.parent.mkdir(parents=True, exist_ok=True)
        evaluator_latest.write_text(
            json.dumps(
                {
                    "overall": "HEALTHY",
                    "metadata": {"generated_at": "2026-04-10T00:05:00Z"},
                    "handoff_file": str((sandbox_root / "artifacts" / "harness-eval" / "latest-handoff.json").resolve()),
                    "progress_file": str((sandbox_root / "artifacts" / "harness-eval" / "latest-progress.md").resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        payload = agent_heartbeat.build_heartbeat_payload(root_dir=sandbox_root)
        outputs = agent_heartbeat.write_heartbeat_artifacts(
            payload,
            root_dir=sandbox_root,
            artifact_dir="artifacts/memory",
            output_markdown="docs/agent/heartbeat.md",
        )

        markdown = Path(outputs["markdown_file"]).read_text(encoding="utf-8")
        json_payload = json.loads(Path(outputs["json_file"]).read_text(encoding="utf-8"))
        self.assertEqual("heartbeat", json_payload["kind"])
        self.assertEqual("H5-3 Global Heartbeat Memory", json_payload["active_phase"]["current_priority"])
        self.assertTrue(any(item["task"] == "report-solution" for item in json_payload["missions"]))
        self.assertTrue(any(item["kind"] == "evaluator" for item in json_payload["latest_runs"]))
        self.assertIn("DeepVision Heartbeat", markdown)
        self.assertIn("H5-3 Global Heartbeat Memory", markdown)
        self.assertIn("report-solution-share-fix-mission", markdown)

    def test_agent_heartbeat_collects_nested_stability_release_latest(self):
        sandbox_root = self.sandbox_root / "heartbeat-stability-release"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        release_base = sandbox_root / "artifacts" / "harness-runs" / "stability-local" / "release-repeat"
        release_base.mkdir(parents=True, exist_ok=True)
        self._write_history_run(
            root_dir=sandbox_root,
            rel_base="artifacts/harness-runs/stability-local/release-repeat",
            run_name="20260411T170000Z-pid70001",
            summary_payload={
                "overall": "READY_WITH_WARNINGS",
                "duration_ms": 44506.25,
                "summary": {"PASS": 5, "WARN": 1, "FAIL": 0},
                "results": [
                    {"name": "browser_smoke", "status": "WARN"},
                ],
            },
            generated_at="2026-04-11T17:00:00Z",
        )
        (release_base / "latest.json").write_text(
            json.dumps(
                {
                    "overall": "READY_WITH_WARNINGS",
                    "generated_at": "2026-04-11T17:00:00Z",
                    "duration_ms": 44506.25,
                    "progress_file": str((release_base / "latest-progress.md").resolve()),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        payload = agent_heartbeat.build_heartbeat_payload(root_dir=sandbox_root)
        run_map = {item["kind"]: item for item in payload["latest_runs"]}
        self.assertIn("harness-stability-release", run_map)
        self.assertEqual("READY_WITH_WARNINGS", run_map["harness-stability-release"]["overall"])
        self.assertEqual(44506.25, run_map["harness-stability-release"]["duration_ms"])
        self.assertTrue(
            str(run_map["harness-stability-release"]["latest_json"]).endswith(
                "artifacts/harness-runs/stability-local/release-repeat/latest.json"
            )
        )

    def test_agent_autodream_builds_best_practices_payload(self):
        heartbeat_payload = {
            "active_phase": {
                "name": "phase6",
                "current_priority": "H6-4 AutoDream Lite",
                "progress_file": "docs/agent/harness-progress-phase6.md",
                "plan_file": "docs/agent/harness-iteration-plan-phase6.md",
            },
            "latest_runs": [
                {"kind": "harness", "overall": "READY", "latest_json": "artifacts/harness-runs/latest.json", "generated_at": "2026-04-10T00:00:00Z"},
                {"kind": "evaluator", "overall": "HEALTHY", "latest_json": "artifacts/harness-eval/latest.json", "generated_at": "2026-04-10T00:05:00Z"},
                {"kind": "ci-browser-smoke", "overall": "READY", "latest_json": "artifacts/ci/browser-smoke/latest.json", "generated_at": "2026-04-10T00:10:00Z"},
            ],
        }
        gardening_payload = {
            "overall": "HEALTHY",
            "checks": [
                {"name": "task_playbooks_synced", "status": "PASS"},
                {"name": "planner_mission_materialization", "status": "PASS"},
                {"name": "high_risk_contract_coverage", "status": "PASS"},
                {"name": "hierarchical_agents_coverage", "status": "PASS"},
            ],
            "recommendations": [],
        }
        payload = agent_autodream.build_best_practices_payload(
            heartbeat_payload=heartbeat_payload,
            gardening_payload=gardening_payload,
        )
        self.assertEqual("best_practices", payload["kind"])
        self.assertEqual("phase6", payload["active_phase"]["name"])
        self.assertTrue(any("agent_autodream.py" in item for item in payload["recommended_commands"]))
        self.assertTrue(payload["stable_practices"])
        self.assertTrue(payload["stable_run_highlights"])

    def test_agent_autodream_main_writes_report_and_memory_notes(self):
        sandbox_root = self.sandbox_root / "autodream-root"
        sandbox_root.mkdir(parents=True, exist_ok=True)
        gardening_payload = {
            "kind": "doc_gardening",
            "generated_at": "2026-04-10T00:00:00Z",
            "overall": "HEALTHY",
            "summary": {"PASS": 6, "WARN": 0, "FAIL": 0},
            "checks": [
                {"name": "task_playbooks_synced", "status": "PASS", "detail": "ok", "highlights": [], "recommendations": []},
                {"name": "planner_mission_materialization", "status": "PASS", "detail": "tasks=8 planner=8 mission=8", "highlights": [], "recommendations": []},
                {"name": "high_risk_contract_coverage", "status": "PASS", "detail": "high_risk=5 covered=5", "highlights": [], "recommendations": []},
                {"name": "hierarchical_agents_coverage", "status": "PASS", "detail": "required=5 materialized=5", "highlights": [], "recommendations": []},
            ],
            "recommendations": [],
        }
        heartbeat_payload = {
            "kind": "heartbeat",
            "generated_at": "2026-04-10T00:01:00Z",
            "active_phase": {
                "name": "phase6",
                "current_priority": "H6-4 AutoDream Lite",
                "progress_file": "docs/agent/harness-progress-phase6.md",
                "plan_file": "docs/agent/harness-iteration-plan-phase6.md",
            },
            "stable_entrypoints": {
                "docs": ["AGENTS.md", "docs/agent/heartbeat.md", "docs/agent/memory-notes.md"],
                "commands": ["python3 scripts/agent_autodream.py", "python3 scripts/agent_harness.py --profile auto"],
            },
            "capabilities": {
                "task_count": 8,
                "scenario_count": 17,
                "browser_suites": ["minimal", "extended"],
                "agent_entrypoint_count": 6,
            },
            "missions": [],
            "plans": [],
            "latest_runs": [
                {"kind": "harness", "overall": "READY", "latest_json": "artifacts/harness-runs/latest.json", "generated_at": "2026-04-10T00:00:00Z"},
                {"kind": "evaluator", "overall": "HEALTHY", "latest_json": "artifacts/harness-eval/latest.json", "generated_at": "2026-04-10T00:05:00Z"},
            ],
            "notes": ["先看 heartbeat。"],
        }
        doc_dir = sandbox_root / "doc-gardening"
        heartbeat_dir = sandbox_root / "memory"
        heartbeat_md = sandbox_root / "heartbeat.md"
        notes_md = sandbox_root / "memory-notes.md"
        autodream_dir = sandbox_root / "autodream"

        with patch.object(agent_doc_gardener, "build_doc_gardening_report", return_value=gardening_payload), patch.object(
            agent_heartbeat, "build_heartbeat_payload", return_value=heartbeat_payload
        ):
            exit_code = agent_autodream.main(
                [
                    "--doc-gardening-dir",
                    str(doc_dir),
                    "--heartbeat-artifact-dir",
                    str(heartbeat_dir),
                    "--heartbeat-markdown",
                    str(heartbeat_md),
                    "--best-practices-artifact-dir",
                    str(heartbeat_dir),
                    "--best-practices-markdown",
                    str(notes_md),
                    "--artifact-dir",
                    str(autodream_dir),
                ]
            )

        self.assertEqual(0, exit_code)
        self.assertTrue((doc_dir / "latest.json").exists())
        self.assertTrue((heartbeat_dir / "latest.json").exists())
        self.assertTrue((heartbeat_dir / "best-practices-latest.json").exists())
        self.assertTrue((autodream_dir / "latest.json").exists())
        self.assertTrue(heartbeat_md.exists())
        self.assertTrue(notes_md.exists())
        autodream_payload = json.loads((autodream_dir / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual("autodream_lite", autodream_payload["kind"])
        self.assertEqual("HEALTHY", autodream_payload["overall"])
        notes_markdown = notes_md.read_text(encoding="utf-8")
        self.assertIn("DeepVision Memory Notes", notes_markdown)
        self.assertIn("H6-4 AutoDream Lite", notes_markdown)

    def test_agent_eval_single_case_pass_does_not_emit_false_hotspot(self):
        scenario_root = self.sandbox_root / "eval-scenarios-pass"
        scenario_dir = scenario_root / "security"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "single-pass.json").write_text(
            json.dumps(
                {
                    "name": "single-pass",
                    "category": "security",
                    "description": "验证单用例通过时不会误报 failure hotspot",
                    "tags": ["nightly"],
                    "cases": [
                        {
                            "test_id": "tests.fake.SecurityTests.test_pass",
                            "label": "通过用例",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        fake_execution = agent_eval.SuiteExecution(
            command=["python3", "-m", "unittest", "tests.fake.SecurityTests.test_pass"],
            returncode=0,
            stdout=".\nOK\n",
            stderr="",
        )

        with patch.object(agent_eval, "run_suite_process", return_value=fake_execution):
            payload, _artifact_paths, exit_code = agent_eval.run_eval(
                scenarios_root=scenario_root,
                tags=["nightly"],
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("HEALTHY", payload["overall"])
        self.assertEqual([], payload["failure_hotspots"])
        self.assertEqual([], payload["results"][0]["failure_hotspots"])

    def test_agent_eval_supports_browser_smoke_executor(self):
        scenario_root = self.sandbox_root / "eval-browser-scenarios"
        scenario_dir = scenario_root / "browser"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "browser-smoke-minimal.json").write_text(
            json.dumps(
                {
                    "name": "browser-smoke-minimal",
                    "category": "browser",
                    "description": "验证 evaluator 可执行 browser smoke 场景",
                    "tags": ["nightly", "browser"],
                    "budgets": {"max_duration_ms": 120000},
                    "executor": {
                        "type": "browser_smoke",
                        "suite": "minimal",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        fake_payload = {
            "overall": "READY",
            "summary": {"PASS": 3, "WARN": 0, "FAIL": 0},
            "results": [
                {"scenario_id": "help-docs", "label": "帮助页", "status": "PASS", "detail": "ok", "highlights": ["help ok"]},
            ],
        }

        with patch.object(agent_eval.agent_browser_smoke, "run_browser_smoke", return_value=(fake_payload, 0)):
            payload, _artifact_paths, exit_code = agent_eval.run_eval(
                scenarios_root=scenario_root,
                tags=["browser"],
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("HEALTHY", payload["overall"])
        self.assertEqual("browser_smoke", payload["results"][0]["executor"])
        self.assertEqual("suite=minimal", payload["results"][0]["target"])

    def test_agent_eval_supports_workflow_executor(self):
        scenario_root = self.sandbox_root / "eval-workflow-scenarios"
        scenario_dir = scenario_root / "workflow"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "report-solution-preview.json").write_text(
            json.dumps(
                {
                    "name": "report-solution-preview",
                    "category": "workflow",
                    "description": "验证 evaluator 可执行 task workflow 场景",
                    "tags": ["nightly", "workflow"],
                    "budgets": {"max_duration_ms": 120000},
                    "executor": {
                        "type": "workflow",
                        "task": "report-solution",
                        "execute_mode": "preview",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        fake_payload = {
            "overall": "READY",
            "summary": {"PASS": 2, "FAIL": 0, "BLOCKED": 0, "MANUAL": 0, "PLANNED": 0, "SKIP": 1},
            "precondition_results": [],
            "step_results": [
                {"id": "targeted-tests", "title": "跑方案页专项回归", "status": "PASS", "detail": "执行成功", "highlights": ["OK"]},
                {"id": "smoke", "title": "补跑最小主链路 harness", "status": "PASS", "detail": "执行成功", "highlights": ["smoke ok"]},
            ],
        }

        with patch.object(agent_eval.agent_workflow, "run_task_workflow", return_value=(fake_payload, 0)):
            payload, _artifact_paths, exit_code = agent_eval.run_eval(
                scenarios_root=scenario_root,
                tags=["workflow"],
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("HEALTHY", payload["overall"])
        self.assertEqual("workflow", payload["results"][0]["executor"])
        self.assertEqual("task=report-solution execute=preview", payload["results"][0]["target"])

    def test_agent_eval_workflow_failure_writes_step_stderr_excerpt(self):
        scenario_root = self.sandbox_root / "eval-workflow-failure-scenarios"
        scenario_dir = scenario_root / "workflow"
        artifact_root = self.sandbox_root / "eval-workflow-failure-artifacts"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "report-solution-preview.json").write_text(
            json.dumps(
                {
                    "name": "report-solution-preview",
                    "category": "workflow",
                    "description": "验证 workflow 失败时会落 step 级错误日志",
                    "tags": ["nightly", "workflow"],
                    "budgets": {"max_duration_ms": 120000},
                    "executor": {
                        "type": "workflow",
                        "task": "report-solution",
                        "execute_mode": "preview",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        fake_payload = {
            "overall": "BLOCKED",
            "summary": {"PASS": 0, "FAIL": 1, "BLOCKED": 0, "MANUAL": 0, "PLANNED": 0, "SKIP": 0},
            "precondition_results": [],
            "step_results": [
                {
                    "id": "targeted-tests",
                    "title": "跑方案页专项回归",
                    "status": "FAIL",
                    "detail": "执行失败，returncode=1",
                    "command": "uv run --with requests python3 -m unittest -q tests.test_solution_payload",
                    "highlights": [
                        "ERROR: test_historical_interview_markdown_extracts_overview_and_structured_fields",
                        "Traceback (most recent call last):",
                    ],
                    "stdout": "E\n",
                    "stderr": "ERROR: test_historical_interview_markdown_extracts_overview_and_structured_fields\nTraceback (most recent call last):\nAssertionError: expected fixture\n",
                }
            ],
        }

        with patch.object(agent_eval.agent_workflow, "run_task_workflow", return_value=(fake_payload, 1)):
            payload, artifact_paths, exit_code = agent_eval.run_eval(
                scenarios_root=scenario_root,
                tags=["workflow"],
                artifact_dir=str(artifact_root),
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("BLOCKED", payload["overall"])
        stderr_log = Path(artifact_paths["run_dir"]) / "report-solution-preview.attempt1.stderr.log"
        self.assertTrue(stderr_log.exists())
        stderr_text = stderr_log.read_text(encoding="utf-8")
        self.assertIn("=== FAIL 跑方案页专项回归 ===", stderr_text)
        self.assertIn("AssertionError: expected fixture", stderr_text)
        self.assertIn("uv run --with requests", stderr_text)

    def test_agent_observe_collects_runtime_snapshot_from_temp_workspace(self):
        observe_root = self.sandbox_root / "observe-root"
        (observe_root / "web").mkdir(parents=True, exist_ok=True)
        (observe_root / "data" / "metrics").mkdir(parents=True, exist_ok=True)
        (observe_root / "data" / "operations" / "ownership-migrations" / "backup-001").mkdir(parents=True, exist_ok=True)
        (observe_root / "artifacts" / "harness-eval" / "run-101").mkdir(parents=True, exist_ok=True)
        (observe_root / "artifacts" / "harness-runs" / "run-001").mkdir(parents=True, exist_ok=True)
        (observe_root / "artifacts" / "harness-runs" / "run-000").mkdir(parents=True, exist_ok=True)

        env_file = observe_root / "web" / ".env.local"
        env_file.write_text(
            "\n".join(
                [
                    "DEBUG_MODE=true",
                    "ENABLE_AI=true",
                    "SMS_PROVIDER=mock",
                    "INSTANCE_SCOPE_KEY=observe-scope",
                    "AUTH_DB_PATH=data/auth/users.db",
                    "LICENSE_DB_PATH=data/auth/licenses.db",
                    "META_INDEX_DB_PATH=data/meta_index.db",
                    "ADMIN_PHONE_NUMBERS=13700000000,13800000000",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (observe_root / "web" / "config.py").write_text("DEBUG = True\n", encoding="utf-8")
        (observe_root / "web" / "site-config.js").write_text("window.DV={};\n", encoding="utf-8")

        self._make_sqlite_db(
            observe_root / "data" / "auth" / "users.db",
            [
                "CREATE TABLE users (id INTEGER PRIMARY KEY, account TEXT)",
                "CREATE TABLE wechat_identities (id INTEGER PRIMARY KEY, user_id INTEGER)",
            ],
            [
                ("INSERT INTO users(id, account) VALUES (?, ?)", (1, "user-a")),
                ("INSERT INTO users(id, account) VALUES (?, ?)", (2, "user-b")),
                ("INSERT INTO wechat_identities(id, user_id) VALUES (?, ?)", (1, 1)),
            ],
        )
        self._make_sqlite_db(
            observe_root / "data" / "auth" / "licenses.db",
            [
                "CREATE TABLE licenses (id INTEGER PRIMARY KEY, status TEXT)",
            ],
            [
                ("INSERT INTO licenses(id, status) VALUES (?, ?)", (1, "active")),
                ("INSERT INTO licenses(id, status) VALUES (?, ?)", (2, "revoked")),
            ],
        )
        self._make_sqlite_db(
            observe_root / "data" / "meta_index.db",
            [
                "CREATE TABLE session_store (id INTEGER PRIMARY KEY)",
                "CREATE TABLE report_store (id INTEGER PRIMARY KEY)",
                "CREATE TABLE summary_cache_store (doc_hash TEXT, summary_text TEXT)",
                "CREATE TABLE runtime_metrics_store (metric_key TEXT PRIMARY KEY, payload_json TEXT)",
            ],
            [
                ("INSERT INTO session_store(id) VALUES (?)", (1,)),
                ("INSERT INTO report_store(id) VALUES (?)", (1,)),
                ("INSERT INTO summary_cache_store(doc_hash, summary_text) VALUES (?, ?)", ("doc-a", "summary-a")),
                (
                    "INSERT INTO runtime_metrics_store(metric_key, payload_json) VALUES (?, ?)",
                    (
                        "api_metrics",
                        json.dumps(
                            {
                                "calls": [
                                    {
                                        "timestamp": "2026-04-07T03:00:00Z",
                                        "event_kind": "api_call",
                                        "type": "generate_report",
                                        "success": True,
                                        "timeout": False,
                                        "error": "",
                                    },
                                    {
                                        "timestamp": "2026-04-07T03:05:00Z",
                                        "event_kind": "api_call",
                                        "type": "generate_report",
                                        "success": False,
                                        "timeout": False,
                                        "error": "boom",
                                        "stage": "draft_gen",
                                    },
                                ],
                                "summary": {
                                    "total_calls": 2,
                                    "avg_response_time": 120.5,
                                    "avg_queue_wait_ms": 10.0,
                                    "total_timeouts": 0,
                                    "total_cache_hits": 1,
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ),
                ),
            ],
        )

        (observe_root / "data" / "operations" / "ownership-migrations" / "backup-001" / "metadata.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T02:50:00Z",
                    "mode": "apply",
                    "scope": "unowned",
                    "target_user": {"account": "13700000000"},
                    "sessions": {"updated": 3},
                    "reports": {"updated": 2},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "data" / "operations" / "cloud-check.json").write_text("{\"ok\":true}\n", encoding="utf-8")
        startup_snapshot_file = observe_root / "data" / "operations" / "runtime-startup" / "latest.json"
        startup_snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        startup_snapshot_file.write_text(
            json.dumps(
                {
                    "initialized": True,
                    "reason": "unit_test",
                    "started_at": "2026-04-07T02:40:00Z",
                    "completed_at": "2026-04-07T02:40:01Z",
                    "total_ms": 321.45,
                    "phases": [
                        {"name": "auth_db", "elapsed_ms": 10.0},
                        {"name": "license_db", "elapsed_ms": 11.0},
                        {"name": "meta_index_schema", "elapsed_ms": 12.0},
                    ],
                    "failed_phase": "",
                    "error": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "run-000" / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:00:00Z",
                    "overall": "READY",
                    "task": {"name": "report-solution"},
                    "summary": {"PASS": 3, "WARN": 0, "FAIL": 0, "SKIP": 0},
                    "results": [{"name": "smoke", "status": "PASS"}],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "run-000" / "handoff.json").write_text(
            json.dumps(
                {
                    "kind": "harness",
                    "overall": "READY",
                    "blockers": [],
                    "todo": [],
                    "next_steps": ["继续扩覆盖"],
                    "resume_commands": [
                        "python3 scripts/agent_harness.py --task report-solution --profile auto --artifact-dir artifacts/harness-runs"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "run-001" / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:10:00Z",
                    "overall": "BLOCKED",
                    "task": {"name": "config-center"},
                    "summary": {"PASS": 2, "WARN": 0, "FAIL": 1, "SKIP": 0},
                    "results": [{"name": "smoke", "status": "FAIL"}],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "run-001" / "handoff.json").write_text(
            json.dumps(
                {
                    "kind": "harness",
                    "overall": "BLOCKED",
                    "blockers": ["smoke: smoke failed"],
                    "todo": ["先修 smoke"],
                    "next_steps": ["查看 failure-summary.md"],
                    "resume_commands": [
                        "python3 scripts/agent_harness.py --task config-center --workflow-execute preview --artifact-dir artifacts/harness-runs"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "run-002").mkdir(parents=True, exist_ok=True)
        (observe_root / "artifacts" / "harness-runs" / "run-002" / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:15:00Z",
                    "overall": "BLOCKED",
                    "task": {"name": "config-center"},
                    "summary": {"PASS": 2, "WARN": 0, "FAIL": 1, "SKIP": 0},
                    "results": [{"name": "guardrails", "status": "FAIL"}],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "run-002" / "handoff.json").write_text(
            json.dumps(
                {
                    "kind": "harness",
                    "overall": "BLOCKED",
                    "blockers": ["smoke: smoke failed"],
                    "todo": ["补充 config-center 回归"],
                    "next_steps": ["先复跑 smoke"],
                    "resume_commands": [
                        "python3 scripts/agent_harness.py --task config-center --workflow-execute preview --artifact-dir artifacts/harness-runs"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-eval" / "run-100").mkdir(parents=True, exist_ok=True)
        (observe_root / "artifacts" / "harness-eval" / "run-100" / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:05:00Z",
                    "overall": "HEALTHY",
                    "filters": {"tags": ["nightly"]},
                    "summary": {"PASS": 2, "FLAKY": 0, "FAIL": 0, "budget_exceeded": 0},
                    "slowest_scenarios": [
                        {
                            "name": "access-boundaries",
                            "category": "security",
                            "max_duration_ms": 420.0,
                            "budget_exceeded": False,
                        }
                    ],
                    "results": [
                        {
                            "category": "security",
                            "name": "access-boundaries",
                            "status": "PASS",
                            "stats": {"max_duration_ms": 420.0, "budget_exceeded": False},
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-eval" / "run-100" / "handoff.json").write_text(
            json.dumps(
                {
                    "kind": "evaluator",
                    "overall": "HEALTHY",
                    "blockers": [],
                    "todo": [],
                    "next_steps": ["继续补场景"],
                    "resume_commands": [
                        "python3 scripts/agent_eval.py --scenario access-boundaries --artifact-dir artifacts/harness-eval"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        nested_run_dir = observe_root / "artifacts" / "harness-runs" / "stability-local" / "release-repeat" / "run-003"
        nested_run_dir.mkdir(parents=True, exist_ok=True)
        (nested_run_dir / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:25:00Z",
                    "overall": "BLOCKED",
                    "duration_ms": 12345.67,
                    "summary": {"PASS": 3, "WARN": 0, "FAIL": 1, "SKIP": 0},
                    "results": [
                        {"name": "doctor", "status": "PASS", "detail": "ok"},
                        {"name": "browser_smoke", "status": "FAIL", "detail": "interrupted"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-eval" / "run-101" / "summary.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:20:00Z",
                    "overall": "HEALTHY",
                    "filters": {"tags": ["nightly"]},
                    "summary": {"PASS": 2, "FLAKY": 0, "FAIL": 0, "budget_exceeded": 0},
                    "slowest_scenarios": [
                        {
                            "name": "access-boundaries",
                            "category": "security",
                            "max_duration_ms": 629.31,
                            "budget_exceeded": False,
                        }
                    ],
                    "results": [
                        {
                            "category": "security",
                            "name": "access-boundaries",
                            "status": "PASS",
                            "stats": {"max_duration_ms": 629.31, "budget_exceeded": False},
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-eval" / "run-101" / "handoff.json").write_text(
            json.dumps(
                {
                    "kind": "evaluator",
                    "overall": "HEALTHY",
                    "blockers": [],
                    "todo": [],
                    "next_steps": ["继续补场景"],
                    "resume_commands": [
                        "python3 scripts/agent_eval.py --scenario access-boundaries --artifact-dir artifacts/harness-eval"
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (observe_root / "artifacts" / "harness-runs" / "latest.json").write_text(
            json.dumps(
                {
                    "generated_at": "2026-04-07T03:15:00Z",
                    "run_name": "run-002",
                    "run_dir": str(observe_root / "artifacts" / "harness-runs" / "run-002"),
                    "summary_file": str(observe_root / "artifacts" / "harness-runs" / "run-002" / "summary.json"),
                    "overall": "BLOCKED",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        payload, exit_code = agent_observe.run_observe(
            profile="local",
            env_file=str(env_file),
            recent=3,
            root_dir=observe_root,
        )
        self.assertEqual(0, exit_code)
        self.assertEqual("BLOCKED", payload["overall"])
        item_map = {item["name"]: item for item in payload["items"]}
        self.assertEqual("PASS", item_map["startup_snapshot"]["status"])
        self.assertEqual("operations/runtime-startup", item_map["startup_snapshot"]["data"]["source"])
        self.assertEqual("PASS", item_map["metrics"]["status"])
        self.assertEqual(2, item_map["db_health"]["data"]["auth_db"]["users"])
        self.assertEqual(2, item_map["ownership_history"]["data"]["items"][0]["reports_updated"])
        self.assertEqual("BLOCKED", item_map["harness_runs"]["data"]["latest_pointer"]["overall"])
        self.assertEqual("BLOCKED", item_map["harness_runs"]["data"]["recent_runs"][0]["overall"])
        self.assertEqual(12345.67, item_map["harness_runs"]["data"]["recent_runs"][0]["duration_ms"])
        self.assertIn("latest_ms=12345.67", item_map["harness_runs"]["detail"])
        self.assertEqual("WARN", item_map["history_trends"]["status"])
        self.assertEqual("CHANGED", item_map["history_trends"]["data"]["diffs"]["harness"]["overall"])
        self.assertTrue(any(item["kind"] == "harness" for item in item_map["history_trends"]["data"]["drift_items"]))
        self.assertTrue(any(item["kind"] == "harness-stability-release" for item in item_map["history_trends"]["data"]["latest"]))
        self.assertEqual("PASS", item_map["history_trends"]["data"]["stability_gates"][0]["status"])
        self.assertEqual(12345.67, item_map["history_trends"]["data"]["stability_gates"][0]["duration_ms"])
        self.assertEqual("config-center", item_map["history_trends"]["data"]["problem_tasks"][0]["subject"])
        self.assertEqual("smoke: smoke failed", item_map["history_trends"]["data"]["top_blockers"][0]["text"])
        self.assertEqual("access-boundaries", item_map["history_trends"]["data"]["slow_scenarios"][0]["name"])
        self.assertEqual("harness", item_map["history_trends"]["data"]["consecutive_problems"][0]["kind"])
        self.assertEqual(3, item_map["history_trends"]["data"]["consecutive_problems"][0]["streak"])
        self.assertEqual(2, item_map["history_trends"]["data"]["frequent_blockers"][0]["count"])
        self.assertEqual("access-boundaries", item_map["history_trends"]["data"]["slow_regressions"][0]["name"])
        self.assertGreater(item_map["history_trends"]["data"]["slow_regressions"][0]["delta_ms"], 150)
        self.assertIn("task=config-center", item_map["history_trends"]["detail"])
        self.assertIn("slow=access-boundaries", item_map["history_trends"]["detail"])
        self.assertIn("streak=harness:3", item_map["history_trends"]["detail"])
        self.assertIn("regression=access-boundaries", item_map["history_trends"]["detail"])
        self.assertIn("release_gate=PASS:12345.67", item_map["history_trends"]["detail"])
        self.assertEqual("FAIL", item_map["diagnostic_panel"]["status"])
        self.assertEqual("config-center", item_map["diagnostic_panel"]["data"]["top_problem_task"]["subject"])
        self.assertEqual("smoke: smoke failed", item_map["diagnostic_panel"]["data"]["top_blocker"]["text"])
        self.assertEqual("access-boundaries", item_map["diagnostic_panel"]["data"]["top_slow_scenario"]["name"])
        self.assertEqual(3, item_map["diagnostic_panel"]["data"]["top_consecutive_problem"]["streak"])
        self.assertEqual(2, item_map["diagnostic_panel"]["data"]["top_frequent_blocker"]["count"])
        self.assertEqual("access-boundaries", item_map["diagnostic_panel"]["data"]["top_slow_regression"]["name"])
        self.assertEqual("PASS", item_map["diagnostic_panel"]["data"]["top_stability_gate"]["status"])
        commands = [item["command"] for item in item_map["diagnostic_panel"]["data"]["recommended_commands"]]
        self.assertTrue(any("config-center" in command for command in commands))
        self.assertTrue(any("access-boundaries" in command for command in commands))
        self.assertIn("task=config-center", item_map["diagnostic_panel"]["detail"])
        self.assertIn("slow=access-boundaries", item_map["diagnostic_panel"]["detail"])
        self.assertIn("streak=harness:3", item_map["diagnostic_panel"]["detail"])
        self.assertIn("regression=access-boundaries", item_map["diagnostic_panel"]["detail"])
        self.assertIn("release_gate=PASS:12345.67", item_map["diagnostic_panel"]["detail"])
        self.assertIn("replay=", item_map["diagnostic_panel"]["detail"])

    def test_agent_history_indexes_runs_and_builds_diff(self):
        history_root = self.sandbox_root / "history-root"
        self._write_history_run(
            root_dir=history_root,
            rel_base="artifacts/harness-runs",
            run_name="20260407T010000Z-pid100",
            generated_at="2026-04-07T01:00:00Z",
            summary_payload={
                "overall": "BLOCKED",
                "duration_ms": 1800.0,
                "summary": {"PASS": 1, "WARN": 0, "FAIL": 1, "SKIP": 0},
                "results": [
                    {"name": "doctor", "status": "PASS", "detail": "ok"},
                    {"name": "smoke", "status": "FAIL", "detail": "broken"},
                ],
            },
        )
        self._write_history_run(
            root_dir=history_root,
            rel_base="artifacts/harness-runs/stability-local/release-repeat",
            run_name="20260407T020000Z-pid200",
            generated_at="2026-04-07T02:00:00Z",
            summary_payload={
                "overall": "READY_WITH_WARNINGS",
                "duration_ms": 950.0,
                "task": {"name": "report-solution"},
                "summary": {"PASS": 2, "WARN": 1, "FAIL": 0, "SKIP": 0},
                "results": [
                    {"name": "doctor", "status": "WARN", "detail": "mock sms"},
                    {"name": "smoke", "status": "PASS", "detail": "ok"},
                ],
            },
        )
        self._write_history_run(
            root_dir=history_root,
            rel_base="artifacts/harness-eval",
            run_name="20260407T030000Z-pid300",
            generated_at="2026-04-07T03:00:00Z",
            summary_payload={
                "overall": "HEALTHY",
                "filters": {"tags": ["nightly"]},
                "summary": {"PASS": 2, "FLAKY": 0, "FAIL": 0, "budget_exceeded": 0},
                "results": [
                    {"category": "security", "name": "access-boundaries", "status": "PASS", "detail": "ok"},
                ],
            },
        )

        index_payload = agent_history.build_history_index(kind="all", root_dir=history_root, limit=3)
        self.assertEqual("READY_WITH_WARNINGS", index_payload["collections"]["harness"]["latest"]["overall"])
        self.assertEqual(950.0, index_payload["collections"]["harness"]["latest"]["duration_ms"])
        self.assertEqual("report-solution", index_payload["collections"]["harness"]["latest"]["subject"])
        self.assertEqual("READY_WITH_WARNINGS", index_payload["collections"]["harness-stability-release"]["latest"]["overall"])
        self.assertEqual(950.0, index_payload["collections"]["harness-stability-release"]["latest"]["duration_ms"])
        self.assertEqual("HEALTHY", index_payload["collections"]["evaluator"]["latest"]["overall"])

        diff_payload = agent_history.build_history_diff(kind="harness", root_dir=history_root)
        self.assertEqual("CHANGED", diff_payload["overall"])
        self.assertEqual("BLOCKED", diff_payload["overall_change"]["before"])
        self.assertEqual("READY_WITH_WARNINGS", diff_payload["overall_change"]["after"])
        self.assertTrue(any(item["name"] == "smoke" and item["before"] == "FAIL" and item["after"] == "PASS" for item in diff_payload["changed_results"]))
        self.assertEqual(-1, diff_payload["summary_delta"]["FAIL"])
        self.assertEqual(1, diff_payload["summary_delta"]["WARN"])

    def test_agent_ci_summary_renders_harness_markdown(self):
        artifact_root = self.sandbox_root / "artifacts" / "ci-summary-harness"
        run_dir = artifact_root / "run-001"
        run_dir.mkdir(parents=True, exist_ok=True)

        summary_payload = {
            "overall": "READY",
            "summary": {"PASS": 1, "WARN": 0, "FAIL": 0, "SKIP": 4},
            "results": [
                {
                    "name": "browser_smoke",
                    "status": "PASS",
                    "detail": "suite=extended scenarios=9 fail=0",
                }
            ],
        }
        handoff_payload = {
            "kind": "harness",
            "overall": "READY",
            "todo": [],
            "blockers": [],
            "next_steps": ["当前无阻塞，可继续执行后续开发、交付或人工复核。"],
            "resume_commands": [],
            "docs": [],
            "pointers": {
                "summary_file": str(run_dir / "summary.json"),
                "progress_file": str(run_dir / "progress.md"),
                "failure_summary_file": str(run_dir / "failure-summary.md"),
                "handoff_file": str(run_dir / "handoff.json"),
                "latest_json": str(artifact_root / "latest.json"),
            },
        }
        latest_payload = {
            "generated_at": "2026-04-08T01:00:00Z",
            "run_name": "run-001",
            "run_dir": str(run_dir),
            "summary_file": str(run_dir / "summary.json"),
            "handoff_file": str(run_dir / "handoff.json"),
            "overall": "READY",
        }
        (run_dir / "summary.json").write_text(json.dumps(summary_payload, ensure_ascii=False), encoding="utf-8")
        (run_dir / "handoff.json").write_text(json.dumps(handoff_payload, ensure_ascii=False), encoding="utf-8")
        (artifact_root / "latest.json").write_text(json.dumps(latest_payload, ensure_ascii=False), encoding="utf-8")

        markdown = agent_ci_summary.render_summary_markdown(
            latest_payload=latest_payload,
            summary_payload=summary_payload,
            handoff_payload=handoff_payload,
            title="Browser Smoke Summary",
        )
        self.assertIn("## Browser Smoke Summary", markdown)
        self.assertIn("- Overall: `READY`", markdown)
        self.assertIn("`browser_smoke`: `PASS` | suite=extended scenarios=9 fail=0", markdown)
        self.assertIn("当前无阻塞，可继续执行后续开发、交付或人工复核。", markdown)

    def test_agent_ci_summary_renders_eval_markdown(self):
        artifact_root = self.sandbox_root / "artifacts" / "ci-summary-eval"
        run_dir = artifact_root / "run-001"
        run_dir.mkdir(parents=True, exist_ok=True)

        summary_payload = {
            "overall": "HEALTHY",
            "summary": {"PASS": 1, "FLAKY": 0, "FAIL": 0, "budget_exceeded": 0, "scenarios_total": 1, "attempts_total": 1},
            "results": [
                {
                    "name": "access-boundaries",
                    "status": "PASS",
                    "detail": "attempts=1 pass=1 fail=0 max_ms=629.31",
                }
            ],
            "failure_hotspots": [],
        }
        handoff_payload = {
            "kind": "evaluator",
            "overall": "HEALTHY",
            "todo": [],
            "blockers": [],
            "next_steps": ["当前 evaluator 健康，可继续补充新的事故场景或扩大覆盖。"],
            "resume_commands": [],
            "docs": ["docs/agent/evaluator.md"],
            "pointers": {
                "summary_file": str(run_dir / "summary.json"),
                "progress_file": str(run_dir / "progress.md"),
                "failure_summary_file": str(run_dir / "failure-summary.md"),
                "handoff_file": str(run_dir / "handoff.json"),
                "latest_json": str(artifact_root / "latest.json"),
            },
        }
        latest_payload = {
            "generated_at": "2026-04-08T02:00:00Z",
            "run_name": "run-001",
            "run_dir": str(run_dir),
            "summary_file": str(run_dir / "summary.json"),
            "handoff_file": str(run_dir / "handoff.json"),
            "overall": "HEALTHY",
        }
        (run_dir / "summary.json").write_text(json.dumps(summary_payload, ensure_ascii=False), encoding="utf-8")
        (run_dir / "handoff.json").write_text(json.dumps(handoff_payload, ensure_ascii=False), encoding="utf-8")
        (artifact_root / "latest.json").write_text(json.dumps(latest_payload, ensure_ascii=False), encoding="utf-8")

        markdown = agent_ci_summary.render_summary_markdown(
            latest_payload=latest_payload,
            summary_payload=summary_payload,
            handoff_payload=handoff_payload,
            title="Harness Nightly Summary",
        )
        self.assertIn("## Harness Nightly Summary", markdown)
        self.assertIn("- Kind: `evaluator`", markdown)
        self.assertIn("`access-boundaries`: `PASS` | attempts=1 pass=1 fail=0 max_ms=629.31", markdown)
        self.assertIn("当前 evaluator 健康，可继续补充新的事故场景或扩大覆盖。", markdown)

    def test_agent_static_guardrails_detect_missing_admin_and_owner_checks(self):
        server_file = self.sandbox_root / "static-guardrails" / "server.py"
        server_file.parent.mkdir(parents=True, exist_ok=True)
        server_file.write_text(
            "\n".join(
                [
                    "from flask import Flask, jsonify",
                    "app = Flask(__name__)",
                    "",
                    "def require_admin(func):",
                    "    return func",
                    "",
                    "def require_valid_license(func):",
                    "    return func",
                    "",
                    "@app.route('/api/admin/config-center', methods=['GET'])",
                    "@require_admin",
                    "def admin_get_config_center():",
                    "    return jsonify({'groups': []})",
                    "",
                    "@app.route('/api/admin/config-center/save', methods=['POST'])",
                    "def admin_save_config_center_group():",
                    "    return jsonify({'ok': True})",
                    "",
                    "@app.route('/api/reports/<path:filename>/solution', methods=['GET'])",
                    "def get_report_solution(filename):",
                    "    user_row = get_current_user()",
                    "    if not user_has_level_capability(user_row, 'solution.view'):",
                    "        return jsonify({'error': 'denied'}), 403",
                    "    return jsonify({'ok': True})",
                    "",
                    "@app.route('/api/reports/<path:filename>/solution/share', methods=['POST'])",
                    "def create_report_solution_share(filename):",
                    "    user_row = get_current_user()",
                    "    if not user_has_level_capability(user_row, 'solution.share'):",
                    "        return jsonify({'error': 'denied'}), 403",
                    "    share_record = create_or_get_solution_share(filename, 1)",
                    "    return jsonify(share_record)",
                    "",
                    "@app.route('/api/public/solutions/<share_token>', methods=['GET'])",
                    "def get_public_solution_by_share_token(share_token):",
                    "    record = get_solution_share_record(share_token)",
                    "    payload = {'viewer_capabilities': {'solution_share': True}}",
                    "    return jsonify(payload)",
                    "",
                    "@app.route('/api/admin/ownership-migrations/preview', methods=['POST'])",
                    "@require_admin",
                    "def admin_preview_ownership_migration():",
                    "    summary = run_ownership_migration(apply_mode=True)",
                    "    return jsonify(summary)",
                    "",
                    "@app.route('/api/admin/ownership-migrations/apply', methods=['POST'])",
                    "@require_admin",
                    "def admin_apply_ownership_migration():",
                    "    summary = run_ownership_migration(apply_mode=True)",
                    "    return jsonify(summary)",
                    "",
                    "@app.route('/api/admin/ownership-migrations/rollback', methods=['POST'])",
                    "@require_admin",
                    "def admin_rollback_ownership_migration():",
                    "    return jsonify({'ok': True})",
                    "",
                    "@app.route('/api/admin/licenses/batch', methods=['POST'])",
                    "@require_admin",
                    "def admin_generate_licenses():",
                    "    return jsonify({'ok': True})",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        payload, exit_code = agent_static_guardrails.run_static_guardrails(server_file=server_file)
        self.assertEqual(2, exit_code)
        result_map = {item["name"]: item for item in payload["results"]}
        self.assertEqual("FAIL", result_map["admin_routes_require_admin"]["status"])
        self.assertEqual("FAIL", result_map["license_admin_routes_require_valid_license"]["status"])
        self.assertEqual("FAIL", result_map["solution_view_guard"]["status"])
        self.assertEqual("FAIL", result_map["solution_share_guard"]["status"])
        self.assertEqual("FAIL", result_map["public_solution_readonly"]["status"])
        self.assertEqual("FAIL", result_map["config_center_routes_delegate_helpers"]["status"])
        self.assertEqual("PASS", result_map["frontend_assets_do_not_reference_harness_paths"]["status"])
        self.assertEqual("PASS", result_map["runtime_python_does_not_reference_test_assets"]["status"])
        self.assertEqual("PASS", result_map["runtime_python_does_not_reference_harness_resources"]["status"])
        self.assertEqual("PASS", result_map["business_python_does_not_import_harness"]["status"])
        self.assertEqual("FAIL", result_map["ownership_preview_dry_run"]["status"])
        self.assertEqual("FAIL", result_map["ownership_apply_confirmation"]["status"])
        self.assertEqual("FAIL", result_map["ownership_rollback_requires_backup"]["status"])
        self.assertEqual("方案页查看路由层", result_map["solution_view_guard"]["repair_layer"])
        self.assertTrue(any("get_current_user()" in line for line in result_map["solution_view_guard"]["recommended_actions"]))
        self.assertIn(
            "python3 scripts/agent_harness.py --task report-solution --workflow-execute preview",
            result_map["solution_view_guard"]["rerun_commands"],
        )

    def test_agent_static_guardrails_render_output_includes_action_for_agent(self):
        payload = {
            "server_file": str(ROOT_DIR / "web" / "server.py"),
            "route_count": 42,
            "results": [
                {
                    "name": "solution_view_guard",
                    "status": "FAIL",
                    "detail": "function=get_report_solution",
                    "highlights": ["缺少源码信号: enforce_report_owner_or_404("],
                    "repair_layer": "方案页查看路由层",
                    "recommended_actions": ["在方案页查看路由补回 get_current_user()、solution.view 能力校验和 enforce_report_owner_or_404() 三段式约束。"],
                    "rerun_commands": ["python3 scripts/agent_harness.py --task report-solution --workflow-execute preview"],
                }
            ],
            "summary": {"PASS": 0, "FAIL": 1},
            "overall": "BLOCKED",
        }
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            agent_static_guardrails.render_text_output(payload)
        text = stdout.getvalue()
        self.assertIn("Action for Agent:", text)
        self.assertIn("修复层级: 方案页查看路由层", text)
        self.assertIn("建议动作:", text)
        self.assertIn("推荐复跑:", text)

    def test_agent_static_guardrails_detect_business_importing_harness(self):
        server_file = self.sandbox_root / "static-guardrails-imports" / "web" / "server.py"
        server_file.parent.mkdir(parents=True, exist_ok=True)
        (server_file.parent / "server_modules").mkdir(parents=True, exist_ok=True)
        server_file.write_text(
            "\n".join(
                [
                    "from flask import Flask, jsonify",
                    "app = Flask(__name__)",
                    "",
                    "def require_admin(func):",
                    "    return func",
                    "",
                    "def require_valid_license(func):",
                    "    return func",
                    "",
                    "@app.route('/api/admin/config-center', methods=['GET'])",
                    "@require_admin",
                    "def admin_get_config_center():",
                    "    return jsonify(build_admin_config_center_payload())",
                    "",
                    "@app.route('/api/admin/config-center/save', methods=['POST'])",
                    "@require_admin",
                    "def admin_save_config_center_group():",
                    "    return jsonify(save_admin_config_group(source='env', group_id='base', values={}))",
                    "",
                    "@app.route('/api/reports/<path:filename>/solution', methods=['GET'])",
                    "def get_report_solution(filename):",
                    "    user_row = get_current_user()",
                    "    if not user_has_level_capability(user_row, 'solution.view'):",
                    "        return jsonify({'error': 'denied'}), 403",
                    "    return enforce_report_owner_or_404(filename, 1)",
                    "",
                    "@app.route('/api/reports/<path:filename>/solution/share', methods=['POST'])",
                    "def create_report_solution_share(filename):",
                    "    user_row = get_current_user()",
                    "    if not user_has_level_capability(user_row, 'solution.share'):",
                    "        return jsonify({'error': 'denied'}), 403",
                    "    share_record = create_or_get_solution_share(filename, 1)",
                    "    return jsonify(share_record)",
                    "",
                    "@app.route('/api/public/solutions/<share_token>', methods=['GET'])",
                    "def get_public_solution_by_share_token(share_token):",
                    "    record = get_solution_share_record(share_token)",
                    "    owner_user_id = record.get('owner_user_id')",
                    "    report_name = record.get('report_name')",
                    "    if get_report_owner_id(report_name) != owner_user_id:",
                    "        return jsonify({'error': 'denied'}), 404",
                    "    payload = {'share_mode': 'public', 'report_name': '', 'viewer_capabilities': {'solution_share': False}}",
                    "    response = jsonify(payload)",
                    "    response.headers['X-Robots-Tag'] = 'noindex, nofollow'",
                    "    return response",
                    "",
                    "@app.route('/api/admin/ownership-migrations/preview', methods=['POST'])",
                    "@require_admin",
                    "def admin_preview_ownership_migration():",
                    "    _store_admin_ownership_preview({'ok': True})",
                    "    return jsonify(run_ownership_migration(apply_mode=False))",
                    "",
                    "@app.route('/api/admin/ownership-migrations/apply', methods=['POST'])",
                    "@require_admin",
                    "def admin_apply_ownership_migration():",
                    "    preview = _get_admin_ownership_preview()",
                    "    preview_token = preview.get('token')",
                    "    payload = _serialize_admin_ownership_request_payload({})",
                    "    confirm_phrase = preview.get('confirm_phrase')",
                    "    confirm_text = confirm_phrase",
                    "    return jsonify(run_ownership_migration(apply_mode=True))",
                    "",
                    "@app.route('/api/admin/ownership-migrations/rollback', methods=['POST'])",
                    "@require_admin",
                    "def admin_rollback_ownership_migration():",
                    "    backup_id = 'backup-001'",
                    "    if not backup_id:",
                    "        return jsonify({'error': 'missing'}), 400",
                    "    return jsonify({'ok': True})",
                    "",
                    "@app.route('/api/admin/licenses/batch', methods=['POST'])",
                    "@require_admin",
                    "@require_valid_license",
                    "def admin_generate_licenses():",
                    "    return jsonify({'ok': True})",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (server_file.parent / "server_modules" / "bad_import.py").write_text(
            "\n".join(
                [
                    "from scripts import agent_harness",
                    "",
                    "def use_harness():",
                    "    return agent_harness.determine_overall_status({'PASS': 1})",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        payload, exit_code = agent_static_guardrails.run_static_guardrails(server_file=server_file)
        self.assertEqual(2, exit_code)
        result_map = {item["name"]: item for item in payload["results"]}
        self.assertEqual("FAIL", result_map["business_python_does_not_import_harness"]["status"])
        self.assertEqual("Python 业务模块 import 边界", result_map["business_python_does_not_import_harness"]["repair_layer"])
        self.assertTrue(any("scripts.agent_" in line for line in result_map["business_python_does_not_import_harness"]["highlights"]))
        self.assertIn("python3 scripts/agent_harness.py --profile auto", result_map["business_python_does_not_import_harness"]["rerun_commands"])

    def test_agent_static_guardrails_detect_dependency_chain_violations(self):
        server_file = self.sandbox_root / "static-guardrails-deps" / "web" / "server.py"
        server_file.parent.mkdir(parents=True, exist_ok=True)
        (server_file.parent / "server_modules").mkdir(parents=True, exist_ok=True)
        (server_file.parent / "app_modules").mkdir(parents=True, exist_ok=True)
        server_file.write_text(
            "\n".join(
                [
                    "from flask import Flask, jsonify",
                    "app = Flask(__name__)",
                    "",
                    "def require_admin(func):",
                    "    return func",
                    "",
                    "def require_valid_license(func):",
                    "    return func",
                    "",
                    "@app.route('/api/admin/config-center', methods=['GET'])",
                    "@require_admin",
                    "def admin_get_config_center():",
                    "    return jsonify(build_admin_config_center_payload())",
                    "",
                    "@app.route('/api/admin/config-center/save', methods=['POST'])",
                    "@require_admin",
                    "def admin_save_config_center_group():",
                    "    return jsonify(save_admin_config_group(source='env', group_id='base', values={}))",
                    "",
                    "@app.route('/api/reports/<path:filename>/solution', methods=['GET'])",
                    "def get_report_solution(filename):",
                    "    user_row = get_current_user()",
                    "    if not user_has_level_capability(user_row, 'solution.view'):",
                    "        return jsonify({'error': 'denied'}), 403",
                    "    return enforce_report_owner_or_404(filename, 1)",
                    "",
                    "@app.route('/api/reports/<path:filename>/solution/share', methods=['POST'])",
                    "def create_report_solution_share(filename):",
                    "    user_row = get_current_user()",
                    "    if not user_has_level_capability(user_row, 'solution.share'):",
                    "        return jsonify({'error': 'denied'}), 403",
                    "    share_record = create_or_get_solution_share(filename, 1)",
                    "    return jsonify(share_record)",
                    "",
                    "@app.route('/api/public/solutions/<share_token>', methods=['GET'])",
                    "def get_public_solution_by_share_token(share_token):",
                    "    record = get_solution_share_record(share_token)",
                    "    owner_user_id = record.get('owner_user_id')",
                    "    report_name = record.get('report_name')",
                    "    if get_report_owner_id(report_name) != owner_user_id:",
                    "        return jsonify({'error': 'denied'}), 404",
                    "    payload = {'share_mode': 'public', 'report_name': '', 'viewer_capabilities': {'solution_share': False}}",
                    "    response = jsonify(payload)",
                    "    response.headers['X-Robots-Tag'] = 'noindex, nofollow'",
                    "    return response",
                    "",
                    "@app.route('/api/admin/ownership-migrations/preview', methods=['POST'])",
                    "@require_admin",
                    "def admin_preview_ownership_migration():",
                    "    _store_admin_ownership_preview({'ok': True})",
                    "    return jsonify(run_ownership_migration(apply_mode=False))",
                    "",
                    "@app.route('/api/admin/ownership-migrations/apply', methods=['POST'])",
                    "@require_admin",
                    "def admin_apply_ownership_migration():",
                    "    preview = _get_admin_ownership_preview()",
                    "    preview_token = preview.get('token')",
                    "    payload = _serialize_admin_ownership_request_payload({})",
                    "    confirm_phrase = preview.get('confirm_phrase')",
                    "    confirm_text = confirm_phrase",
                    "    return jsonify(run_ownership_migration(apply_mode=True))",
                    "",
                    "@app.route('/api/admin/ownership-migrations/rollback', methods=['POST'])",
                    "@require_admin",
                    "def admin_rollback_ownership_migration():",
                    "    backup_id = 'backup-001'",
                    "    if not backup_id:",
                    "        return jsonify({'error': 'missing'}), 400",
                    "    return jsonify({'ok': True})",
                    "",
                    "@app.route('/api/admin/licenses/batch', methods=['POST'])",
                    "@require_admin",
                    "@require_valid_license",
                    "def admin_generate_licenses():",
                    "    return jsonify({'ok': True})",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (server_file.parent / "app_modules" / "bad_harness_ref.js").write_text(
            "export const DEBUG_ARTIFACT = 'artifacts/harness-runs/latest.json';\n",
            encoding="utf-8",
        )
        (server_file.parent / "server_modules" / "bad_test_asset.py").write_text(
            "SCENARIO_PATH = 'tests/harness_scenarios/browser/browser-smoke-extended.json'\n",
            encoding="utf-8",
        )
        (server_file.parent / "server_modules" / "bad_harness_resource.py").write_text(
            "MISSION_DOC = 'docs/agent/heartbeat.md'\nTASK_CONFIG = 'resources/harness/tasks/report-solution.json'\n",
            encoding="utf-8",
        )

        payload, exit_code = agent_static_guardrails.run_static_guardrails(server_file=server_file)
        self.assertEqual(2, exit_code)
        result_map = {item["name"]: item for item in payload["results"]}
        self.assertEqual("FAIL", result_map["frontend_assets_do_not_reference_harness_paths"]["status"])
        self.assertEqual("FAIL", result_map["runtime_python_does_not_reference_test_assets"]["status"])
        self.assertEqual("FAIL", result_map["runtime_python_does_not_reference_harness_resources"]["status"])
        self.assertEqual("前端静态资源依赖边界", result_map["frontend_assets_do_not_reference_harness_paths"]["repair_layer"])
        self.assertEqual("Python 运行时与测试资产边界", result_map["runtime_python_does_not_reference_test_assets"]["repair_layer"])
        self.assertEqual("Python 运行时与 harness 资源边界", result_map["runtime_python_does_not_reference_harness_resources"]["repair_layer"])
        self.assertTrue(
            any(
                "bad_harness_ref.js" in line or "artifacts/harness-" in line
                for line in result_map["frontend_assets_do_not_reference_harness_paths"]["highlights"]
            )
        )
        self.assertTrue(
            any("tests/harness_scenarios" in line for line in result_map["runtime_python_does_not_reference_test_assets"]["highlights"])
        )
        self.assertTrue(
            any(
                "bad_harness_resource.py" in line or "resources/harness" in line or "docs/agent/" in line
                for line in result_map["runtime_python_does_not_reference_harness_resources"]["highlights"]
            )
        )
        self.assertIn(
            "python3 scripts/agent_browser_smoke.py --suite extended",
            result_map["frontend_assets_do_not_reference_harness_paths"]["rerun_commands"],
        )
        self.assertIn(
            "python3 scripts/agent_harness.py --profile auto",
            result_map["runtime_python_does_not_reference_test_assets"]["rerun_commands"],
        )
        self.assertIn(
            "python3 scripts/agent_harness.py --profile auto",
            result_map["runtime_python_does_not_reference_harness_resources"]["rerun_commands"],
        )

    def test_agent_static_guardrails_repo_server_passes(self):
        payload, exit_code = agent_static_guardrails.run_static_guardrails()
        self.assertEqual(0, exit_code)
        self.assertEqual("READY", payload["overall"])
        self.assertGreaterEqual(payload["summary"]["PASS"], 13)

    def test_agent_harness_static_guardrails_stage_uses_static_payload(self):
        fake_payload = {
            "overall": "READY",
            "summary": {"PASS": 13, "FAIL": 0},
            "results": [
                {"name": "admin_routes_require_admin", "status": "PASS", "detail": "checked=24 routes missing=0", "highlights": ["所有高风险管理/运维路由都带 require_admin。"]},
                {"name": "config_center_routes_delegate_helpers", "status": "PASS", "detail": "get=admin_get_config_center save=admin_save_config_center_group", "highlights": ["配置中心路由已委托 build_admin_config_center_payload/save_admin_config_group，未在路由层直接写配置文件。"]},
                {"name": "frontend_assets_do_not_reference_harness_paths", "status": "PASS", "detail": "checked=8 frontend files violations=0", "highlights": ["web/ 下前端静态资源未反向引用 harness 路径、工件或测试语料。"]},
                {"name": "runtime_python_does_not_reference_test_assets", "status": "PASS", "detail": "checked=12 python files violations=0", "highlights": ["web/ 下 Python 运行时代码未反向依赖 tests/ 下的 harness 场景、校准样本或测试模块。"]},
                {"name": "runtime_python_does_not_reference_harness_resources", "status": "PASS", "detail": "checked=12 python files violations=0", "highlights": ["web/ 下 Python 运行时代码未反向依赖 harness resources、artifact 或 agent 文档指针。"]},
                {"name": "business_python_does_not_import_harness", "status": "PASS", "detail": "checked=12 python files violations=0", "highlights": ["web/ 下 Python 业务代码未反向依赖 scripts.agent_* harness 脚本。"]},
                {"name": "solution_view_guard", "status": "PASS", "detail": "function=get_report_solution", "highlights": ["已检测到登录、能力校验和 owner 约束。"]},
            ],
        }
        with patch.object(agent_static_guardrails, "run_static_guardrails", return_value=(fake_payload, 0)):
            execution = agent_harness.run_static_guardrails_stage()
        self.assertEqual("static_guardrails", execution.result.name)
        self.assertEqual("PASS", execution.result.status)
        self.assertIn("rules=13", execution.result.detail)
        self.assertTrue(any("require_admin" in line for line in execution.result.highlights))

    def test_agent_harness_static_guardrails_stage_highlights_action_for_agent_on_fail(self):
        fake_payload = {
            "overall": "BLOCKED",
            "summary": {"PASS": 8, "FAIL": 1},
            "results": [
                {
                    "name": "solution_view_guard",
                    "status": "FAIL",
                    "detail": "function=get_report_solution",
                    "highlights": ["缺少源码信号: enforce_report_owner_or_404("],
                    "repair_layer": "方案页查看路由层",
                    "recommended_actions": ["在方案页查看路由补回 get_current_user()、solution.view 能力校验和 enforce_report_owner_or_404() 三段式约束。"],
                    "rerun_commands": ["python3 scripts/agent_harness.py --task report-solution --workflow-execute preview"],
                }
            ],
        }
        with patch.object(agent_static_guardrails, "run_static_guardrails", return_value=(fake_payload, 2)):
            execution = agent_harness.run_static_guardrails_stage()
        self.assertEqual("FAIL", execution.result.status)
        self.assertTrue(any("修复层级" in line for line in execution.result.highlights))
        self.assertTrue(any("建议:" in line for line in execution.result.highlights))
        self.assertTrue(any("复跑:" in line for line in execution.result.highlights))

    def test_agent_doc_gardener_report_contains_expected_checks(self):
        payload = agent_doc_gardener.build_doc_gardening_report()
        self.assertIn(payload["overall"], {"HEALTHY", "ATTENTION_REQUIRED"})
        check_map = {item["name"]: item for item in payload["checks"]}
        self.assertIn("task_playbooks_synced", check_map)
        self.assertIn("doc_index_links", check_map)
        self.assertIn("hierarchical_agents_coverage", check_map)
        self.assertIn("high_risk_contract_coverage", check_map)
        self.assertIn("planner_mission_materialization", check_map)
        self.assertIn("calibration_registry", check_map)

    def test_agent_doc_gardener_writes_report_artifacts(self):
        payload = agent_doc_gardener.build_doc_gardening_report()
        artifact_dir = self.sandbox_root / "doc-gardening"
        files = agent_doc_gardener.write_artifacts(payload, artifact_dir)
        json_path = Path(files["json_file"])
        markdown_path = Path(files["markdown_file"])
        self.assertTrue(json_path.exists())
        self.assertTrue(markdown_path.exists())
        self.assertIn("# DeepVision Doc Gardening Report", markdown_path.read_text(encoding="utf-8"))

    def test_agent_ops_build_status_payload(self):
        payload = agent_ops.build_ops_payload()
        self.assertIn(payload["overall"], {"HEALTHY", "ATTENTION_REQUIRED", "BLOCKED"})
        self.assertEqual("ops_status", payload["kind"])
        self.assertEqual("phase6", payload["phase"]["name"])
        self.assertIn(
            payload["phase"]["current_priority"],
            {"H6-6 Harness Ops Surface", "phase6 已完成，待新阶段计划"},
        )
        self.assertEqual(8, payload["coverage"]["task_count"])
        self.assertEqual(8, payload["coverage"]["planner_meta"])
        self.assertEqual(8, payload["coverage"]["planner_materialized"])
        self.assertEqual(8, payload["coverage"]["mission_meta"])
        self.assertEqual(8, payload["coverage"]["mission_materialized"])
        self.assertGreaterEqual(payload["coverage"]["high_risk_total"], payload["coverage"]["high_risk_contracts"])
        self.assertGreaterEqual(payload["coverage"]["calibration_samples"], 6)
        self.assertTrue(any("agent_ops.py status" in item for item in payload["recommended_commands"]))
        self.assertIn("overall", payload["doc_gardening"])

    def test_agent_ops_task_gap_repo_is_fully_materialized(self):
        gap = agent_ops.build_ops_payload()["task_gap"]
        self.assertEqual("HEALTHY", gap["overall"])
        self.assertFalse(gap["missing"]["planner_meta"])
        self.assertFalse(gap["missing"]["mission_meta"])
        self.assertFalse(gap["missing"]["planner_materialized"])
        self.assertFalse(gap["missing"]["mission_materialized"])
        self.assertFalse(gap["missing"]["contracts"])

    def test_agent_ops_write_artifacts(self):
        payload = agent_ops.build_ops_payload()
        artifact_dir = self.sandbox_root / "ops-artifacts"
        files = agent_ops.write_artifacts(payload, artifact_dir=artifact_dir)
        json_path = Path(files.json_file)
        markdown_path = Path(files.markdown_file)
        latest_json = Path(files.latest_json)
        latest_markdown = Path(files.latest_markdown)
        self.assertTrue(json_path.exists())
        self.assertTrue(markdown_path.exists())
        self.assertTrue(latest_json.exists())
        self.assertTrue(latest_markdown.exists())
        self.assertIn("# DeepVision Harness Ops", markdown_path.read_text(encoding="utf-8"))
        saved_payload = json.loads(latest_json.read_text(encoding="utf-8"))
        self.assertEqual("ops_status", saved_payload["kind"])

    def test_agent_ops_includes_stability_release_lane_and_duration_gate(self):
        heartbeat_payload = {
            "active_phase": {
                "name": "phase6",
                "current_priority": "S6 非功能质量门与可诊断性",
                "progress_file": "docs/agent/harness-stability-progress.md",
                "plan_file": "docs/agent/harness-stability-plan.md",
            },
            "capabilities": {"agent_entrypoint_count": 12, "scenario_count": 21},
            "stable_entrypoints": {"commands": ["python3 scripts/agent_ops.py status"]},
            "latest_runs": [
                {
                    "kind": "harness",
                    "overall": "READY",
                    "generated_at": "2026-04-11T17:05:00Z",
                    "latest_json": "artifacts/harness-runs/latest.json",
                    "duration_ms": 61000.0,
                },
                {
                    "kind": "harness-stability-release",
                    "overall": "READY_WITH_WARNINGS",
                    "generated_at": "2026-04-11T17:10:00Z",
                    "latest_json": "artifacts/harness-runs/stability-local/release-repeat/latest.json",
                    "duration_ms": agent_ops.STABILITY_RELEASE_FAIL_MS + 5000.0,
                },
            ],
        }
        with (
            patch.object(agent_heartbeat, "build_heartbeat_payload", return_value=heartbeat_payload),
            patch.object(
                agent_doc_gardener,
                "build_doc_gardening_report",
                return_value={"overall": "HEALTHY", "summary": {"PASS": 6, "WARN": 0, "FAIL": 0}, "checks": []},
            ),
            patch.object(
                agent_ops,
                "_build_task_gap_payload",
                return_value={
                    "overall": "HEALTHY",
                    "task_count": 8,
                    "planner_meta": 8,
                    "planner_materialized": 8,
                    "mission_meta": 8,
                    "mission_materialized": 8,
                    "high_risk_contracts": 4,
                    "high_risk_total": 4,
                    "missing": {
                        "planner_meta": [],
                        "mission_meta": [],
                        "planner_materialized": [],
                        "mission_materialized": [],
                        "contracts": [],
                    },
                    "tasks": [],
                },
            ),
            patch.object(agent_calibration, "load_calibration_samples", return_value=[{"id": "c1"}] * 6),
            patch.object(
                agent_history,
                "build_history_diff",
                side_effect=[
                    {"overall": "UNCHANGED", "changed_results": []},
                    {"overall": "UNCHANGED", "changed_results": []},
                    {"overall": "UNCHANGED", "changed_results": []},
                ],
            ),
        ):
            payload = agent_ops.build_ops_payload(root_dir=self.sandbox_root)

        latest_run_map = {item["kind"]: item for item in payload["latest_runs"]["latest_runs"]}
        self.assertIn("harness-stability-release", latest_run_map)
        self.assertEqual(
            agent_ops.STABILITY_RELEASE_WARN_MS,
            payload["latest_runs"]["stability_gates"]["release_max_duration_warn_ms"],
        )
        self.assertEqual(
            agent_ops.STABILITY_RELEASE_FAIL_MS,
            payload["latest_runs"]["stability_gates"]["release_max_duration_fail_ms"],
        )
        blocker_text = "\n".join(payload["latest_runs"]["blockers"])
        self.assertIn("stability-local-release", blocker_text)
        self.assertIn("duration_ms", blocker_text)
        markdown = agent_ops.render_status_markdown(payload)
        self.assertIn("stability-local-release", markdown)
        self.assertIn("duration_ms=", markdown)
        self.assertIn("稳定性门槛", markdown)

    def test_agent_doc_gardener_reports_blocked_when_playbooks_drift(self):
        with patch.object(agent_playbook_sync, "check_task_playbooks", return_value=["report-solution: playbook 内容已漂移"]):
            payload = agent_doc_gardener.build_doc_gardening_report()
        self.assertEqual("BLOCKED", payload["overall"])
        check_map = {item["name"]: item for item in payload["checks"]}
        self.assertEqual("FAIL", check_map["task_playbooks_synced"]["status"])
        self.assertTrue(any("agent_playbook_sync.py" in line for line in check_map["task_playbooks_synced"]["recommendations"]))

    def test_agent_browser_smoke_missing_dependency_returns_fail_payload(self):
        with patch.object(
            agent_browser_smoke,
            "_dependency_summary",
            return_value={
                "node_available": True,
                "npm_available": True,
                "uv_available": True,
                "playwright_package_installed": False,
                "runner_exists": True,
            },
        ):
            payload, exit_code = agent_browser_smoke.run_browser_smoke()
        self.assertEqual(2, exit_code)
        self.assertEqual("BLOCKED", payload["overall"])
        self.assertIn("npm install", "\n".join(payload["results"][0]["highlights"]))

    def test_agent_browser_smoke_live_suite_requires_uv(self):
        with patch.object(
            agent_browser_smoke,
            "_dependency_summary",
            return_value={
                "node_available": True,
                "npm_available": True,
                "uv_available": False,
                "playwright_package_installed": True,
                "runner_exists": True,
            },
        ):
            payload, exit_code = agent_browser_smoke.run_browser_smoke(suite_name="live-minimal")
        self.assertEqual(2, exit_code)
        self.assertEqual("BLOCKED", payload["overall"])
        self.assertIn("uv --version", "\n".join(payload["results"][0]["highlights"]))

    def test_agent_harness_browser_smoke_stage_uses_payload(self):
        fake_payload = {
            "overall": "READY",
            "summary": {"PASS": 9, "WARN": 0, "FAIL": 0},
            "results": [
                {"scenario_id": "help-docs", "label": "帮助文档静态页", "status": "PASS", "detail": "标题与帮助文档主文案可见", "highlights": []},
                {"scenario_id": "solution-share", "label": "方案页分享面板", "status": "PASS", "detail": "方案页成功渲染，分享面板可打开并写入匿名只读链接", "highlights": []},
                {"scenario_id": "solution-public-readonly", "label": "方案页公开分享只读", "status": "PASS", "detail": "公开分享模式可渲染，并保持只读边界", "highlights": []},
                {"scenario_id": "login-view", "label": "登录前端视图", "status": "PASS", "detail": "未登录状态会展示登录表单，并明确提示当前短信登录不可用", "highlights": []},
                {"scenario_id": "license-gate-view", "label": "License 门禁前端视图", "status": "PASS", "detail": "已登录但无有效 License 时，会展示 License gate 与绑定入口", "highlights": []},
                {"scenario_id": "license-activate-success", "label": "License 绑定成功后切回业务壳", "status": "PASS", "detail": "License 绑定成功后会退出门禁，并回到访谈会话主页", "highlights": []},
                {"scenario_id": "report-detail-flow", "label": "报告详情与方案入口", "status": "PASS", "detail": "可从报告列表进入报告详情，并看到方案入口按钮与核心报告内容", "highlights": []},
            ],
        }
        with patch.object(agent_browser_smoke, "run_browser_smoke", return_value=(fake_payload, 0)):
            execution = agent_harness.run_browser_smoke_stage(suite_name="extended", install_browser=False)
        self.assertEqual("browser_smoke", execution.result.name)
        self.assertEqual("PASS", execution.result.status)
        self.assertIn("scenarios=9", execution.result.detail)
        self.assertIn("帮助文档静态页", "\n".join(execution.result.highlights))

    def test_agent_harness_observe_stage_uses_observe_payload(self):
        fake_payload = {
            "overall": "DEGRADED",
            "summary": {"PASS": 3, "WARN": 1, "FAIL": 0},
            "items": [
                {"name": "metrics", "detail": "source=runtime_metrics_store total=10 avg_ms=100.0 recent_failures=1"},
                {"name": "ownership_history", "detail": "items=2 latest=backup-001"},
                {"name": "harness_runs", "detail": "runs=3 latest=BLOCKED blocked=1"},
                {"name": "history_trends", "detail": "latest=4 problem=1 warning=0 harness_diff=CHANGED evaluator_diff=UNCHANGED"},
                {"name": "diagnostic_panel", "detail": "task=config-center blocker=smoke: smoke failed slow=access-boundaries replay=python3 scripts/agent_harness.py --task config-center"},
                {"name": "startup_snapshot", "detail": "startup snapshot unavailable"},
            ],
        }
        with patch.object(agent_observe, "run_observe", return_value=(fake_payload, 0)):
            execution = agent_harness.run_observe_stage(profile="auto", env_file="", recent=5)
        self.assertEqual("observe", execution.result.name)
        self.assertEqual("WARN", execution.result.status)
        self.assertIn("overall=DEGRADED", execution.result.detail)
        self.assertTrue(any("source=runtime_metrics_store" in line for line in execution.result.highlights))
        self.assertTrue(any("harness_diff=CHANGED" in line for line in execution.result.highlights))
        self.assertTrue(any("task=config-center" in line for line in execution.result.highlights))

    def test_agent_harness_summarizes_stage_status(self):
        results = [
            agent_harness.HarnessStageResult(name="doctor", status="PASS", exit_code=0, detail="ok"),
            agent_harness.HarnessStageResult(name="guardrails", status="WARN", exit_code=0, detail="warn"),
            agent_harness.HarnessStageResult(name="smoke", status="SKIP", exit_code=0, detail="skip"),
        ]
        summary = agent_harness.summarize_results(results)
        self.assertEqual(1, summary["PASS"])
        self.assertEqual(1, summary["WARN"])
        self.assertEqual(1, summary["SKIP"])
        self.assertEqual("READY_WITH_WARNINGS", agent_harness.determine_overall_status(summary))

        results.append(agent_harness.HarnessStageResult(name="extra", status="FAIL", exit_code=2, detail="fail"))
        failed_summary = agent_harness.summarize_results(results)
        self.assertEqual("BLOCKED", agent_harness.determine_overall_status(failed_summary))

    def test_agent_harness_extracts_diagnostics(self):
        highlights = agent_harness.extract_highlights(
            "line1\nFAIL: sample\nTraceback (most recent call last):\nAssertionError: boom\n"
        )
        self.assertIn("FAIL: sample", highlights)
        self.assertIn("AssertionError: boom", highlights)

    def test_agent_harness_main_outputs_json_summary(self):
        fake_doctor = self._make_harness_execution(
            name="doctor",
            status="WARN",
            exit_code=0,
            detail="doctor warn",
            highlights=["SMS_PROVIDER: mock"],
        )
        fake_static = self._make_harness_execution(
            name="static_guardrails",
            status="PASS",
            exit_code=0,
            detail="static ok",
        )
        fake_guardrails = self._make_harness_execution(
            name="guardrails",
            status="PASS",
            exit_code=0,
            detail="guardrails ok",
        )
        fake_smoke = self._make_harness_execution(
            name="smoke",
            status="PASS",
            exit_code=0,
            detail="smoke ok",
        )

        with patch.object(agent_harness, "run_doctor_stage", return_value=fake_doctor), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=fake_static,
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=[fake_guardrails, fake_smoke],
        ) as run_suite_stage:
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(["--json"])

        self.assertEqual(0, exit_code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("READY_WITH_WARNINGS", payload["overall"])
        self.assertEqual({"PASS": 3, "WARN": 1, "FAIL": 0, "SKIP": 0}, payload["summary"])
        self.assertGreaterEqual(float(payload.get("duration_ms", 0) or 0), 0.0)
        self.assertEqual("doctor", payload["results"][0]["name"])
        self.assertEqual("SMS_PROVIDER: mock", payload["results"][0]["highlights"][0])
        self.assertEqual(2, run_suite_stage.call_count)

    def test_agent_harness_task_profile_applies_defaults_and_renders_workflow(self):
        observed_profiles = []

        def fake_doctor_stage(**kwargs):
            observed_profiles.append(kwargs["profile"])
            return self._make_harness_execution(
                name="doctor",
                status="PASS",
                exit_code=0,
                detail="doctor ok",
            )

        fake_workflow_payload = {
            "overall": "PLANNED",
            "summary": {"PASS": 0, "FAIL": 0, "BLOCKED": 0, "MANUAL": 0, "PLANNED": 1, "SKIP": 0},
            "workflow": {
                "task": "ownership-migration",
                "description": "管理员归属迁移",
                "risk_level": "high",
                "workflow_mode": "preview_first",
                "docs": ["docs/agent/migration.md"],
                "preconditions": [],
                "steps": [
                    {
                        "id": "audit",
                        "title": "审计目标账号当前归属",
                        "command": "python3 scripts/admin_migrate_ownership.py audit --user-account 13700000000 --kinds sessions,reports",
                        "missing_vars": [],
                    }
                ],
                "hidden_apply_steps": [{"id": "apply"}],
                "missing_vars": [],
                "task_vars": {"target_account": "13700000000"},
            },
            "precondition_results": [],
            "step_results": [
                {
                    "id": "audit",
                    "title": "审计目标账号当前归属",
                    "status": "PLANNED",
                    "detail": "python3 scripts/admin_migrate_ownership.py audit --user-account 13700000000 --kinds sessions,reports",
                    "command": "python3 scripts/admin_migrate_ownership.py audit --user-account 13700000000 --kinds sessions,reports",
                }
            ],
        }

        with patch.object(agent_harness, "run_doctor_stage", side_effect=fake_doctor_stage), patch.object(
            agent_harness.agent_workflow,
            "run_task_workflow",
            return_value=(fake_workflow_payload, 0),
        ), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=self._make_harness_execution(name="static_guardrails", status="PASS", exit_code=0, detail="static ok"),
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=[
                self._make_harness_execution(name="guardrails", status="PASS", exit_code=0, detail="guardrails ok"),
                self._make_harness_execution(name="smoke", status="PASS", exit_code=0, detail="smoke ok"),
            ],
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(
                    [
                        "--task",
                        "ownership-migration",
                        "--task-var",
                        "target_account=13700000000",
                        "--json",
                    ]
                )

        self.assertEqual(0, exit_code)
        self.assertEqual(["auto"], observed_profiles)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("ownership-migration", payload["task"]["name"])
        self.assertEqual("high", payload["task"]["risk_level"])
        workflow_result = next(item for item in payload["results"] if item["name"] == "workflow")
        self.assertEqual("PASS", workflow_result["status"])
        self.assertIn("task=ownership-migration", workflow_result["detail"])
        self.assertTrue(any("admin_migrate_ownership.py audit" in line for line in workflow_result["highlights"]))
        self.assertTrue(any("已隐藏" in line for line in workflow_result["highlights"]))

    def test_agent_harness_can_append_browser_smoke_stage(self):
        with patch.object(
            agent_harness,
            "run_doctor_stage",
            return_value=self._make_harness_execution(name="doctor", status="PASS", exit_code=0, detail="doctor ok"),
        ), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=self._make_harness_execution(name="static_guardrails", status="PASS", exit_code=0, detail="static ok"),
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=[
                self._make_harness_execution(name="guardrails", status="PASS", exit_code=0, detail="guardrails ok"),
                self._make_harness_execution(name="smoke", status="PASS", exit_code=0, detail="smoke ok"),
            ],
        ), patch.object(
            agent_harness,
            "run_browser_smoke_stage",
            return_value=self._make_harness_execution(name="browser_smoke", status="PASS", exit_code=0, detail="browser ok"),
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(["--browser-smoke", "--json"])

        self.assertEqual(0, exit_code)
        payload = json.loads(stdout.getvalue())
        browser_result = next(item for item in payload["results"] if item["name"] == "browser_smoke")
        self.assertEqual("PASS", browser_result["status"])

    def test_agent_harness_stability_local_core_profile_applies_lane_defaults(self):
        observed_doctor_profiles = []
        observed_observe_profiles = []
        observed_guardrails_suites = []
        observed_browser_suites = []

        def fake_doctor_stage(**kwargs):
            observed_doctor_profiles.append(kwargs["profile"])
            return self._make_harness_execution(name="doctor", status="PASS", exit_code=0, detail="doctor ok")

        def fake_observe_stage(**kwargs):
            observed_observe_profiles.append(kwargs["profile"])
            return self._make_harness_execution(name="observe", status="PASS", exit_code=0, detail="observe ok")

        def fake_suite_stage(**kwargs):
            observed_guardrails_suites.append((kwargs["stage_name"], kwargs["suite_name"]))
            return self._make_harness_execution(name=kwargs["stage_name"], status="PASS", exit_code=0, detail=f"{kwargs['stage_name']} ok")

        def fake_browser_stage(**kwargs):
            observed_browser_suites.append(kwargs["suite_name"])
            return self._make_harness_execution(name="browser_smoke", status="PASS", exit_code=0, detail="browser ok")

        with patch.object(agent_harness, "run_doctor_stage", side_effect=fake_doctor_stage), patch.object(
            agent_harness,
            "run_observe_stage",
            side_effect=fake_observe_stage,
        ), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=self._make_harness_execution(name="static_guardrails", status="PASS", exit_code=0, detail="static ok"),
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=fake_suite_stage,
        ), patch.object(
            agent_harness,
            "run_browser_smoke_stage",
            side_effect=fake_browser_stage,
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(["--profile", "stability-local-core", "--json"])

        self.assertEqual(0, exit_code)
        self.assertEqual(["auto"], observed_doctor_profiles)
        self.assertEqual(["auto"], observed_observe_profiles)
        self.assertEqual(
            [("guardrails", "extended"), ("smoke", "extended")],
            observed_guardrails_suites,
        )
        self.assertEqual(["extended"], observed_browser_suites)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("READY", payload["overall"])
        stage_names = [item["name"] for item in payload["results"]]
        self.assertIn("observe", stage_names)
        self.assertIn("browser_smoke", stage_names)

    def test_agent_harness_stability_local_release_profile_uses_live_minimal_browser_suite(self):
        observed_browser_suites = []

        with patch.object(
            agent_harness,
            "run_doctor_stage",
            return_value=self._make_harness_execution(name="doctor", status="PASS", exit_code=0, detail="doctor ok"),
        ), patch.object(
            agent_harness,
            "run_observe_stage",
            return_value=self._make_harness_execution(name="observe", status="PASS", exit_code=0, detail="observe ok"),
        ), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=self._make_harness_execution(name="static_guardrails", status="PASS", exit_code=0, detail="static ok"),
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=[
                self._make_harness_execution(name="guardrails", status="PASS", exit_code=0, detail="guardrails ok"),
                self._make_harness_execution(name="smoke", status="PASS", exit_code=0, detail="smoke ok"),
            ],
        ), patch.object(
            agent_harness,
            "run_browser_smoke_stage",
            side_effect=lambda **kwargs: observed_browser_suites.append(kwargs["suite_name"]) or self._make_harness_execution(
                name="browser_smoke",
                status="PASS",
                exit_code=0,
                detail="browser ok",
            ),
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(["--profile", "stability-local-release", "--json"])

        self.assertEqual(0, exit_code)
        self.assertEqual(["live-minimal"], observed_browser_suites)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("READY", payload["overall"])

    def test_agent_workflow_preview_executes_safe_steps_and_skips_apply(self):
        profile = agent_profiles.get_task_profile("ownership-migration")
        fake_suite_execution = agent_workflow.SuiteExecution(
            command=["uv", "run", "python3", "-m", "unittest", "-q", "tests.sample.case"],
            returncode=0,
            stdout=".\nOK\n",
            stderr="",
        )
        workflow_root = self.sandbox_root / "workflow-preview"
        workflow_root.mkdir(parents=True, exist_ok=True)
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / ".env.local").write_text("ADMIN_PHONE_NUMBERS=13700000000\n", encoding="utf-8")
        self._make_sqlite_db(
            workflow_root / "data" / "auth" / "users.db",
            ["CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, phone TEXT, created_at TEXT)"],
            [("INSERT INTO users(id, email, phone, created_at) VALUES (?, ?, ?, ?)", (7, "", "13700000000", "2026-04-07T00:00:00Z"))],
        )

        def fake_execute(step, *, root_dir):
            if str(step.get("id") or "").strip() == "audit":
                return {"returncode": 0, "stdout": "audit ok\n", "stderr": "", "duration_ms": 10.0, "highlights": ["audit ok"]}
            preview_artifact = Path(root_dir) / "artifacts" / "harness-runs" / "ownership-migration-preview.json"
            preview_artifact.parent.mkdir(parents=True, exist_ok=True)
            preview_artifact.write_text("{}", encoding="utf-8")
            return {"returncode": 0, "stdout": "preview ok\n", "stderr": "", "duration_ms": 11.0, "highlights": ["preview ok"]}

        with patch.object(
            agent_workflow,
            "_execute_step",
            side_effect=fake_execute,
        ) as execute_step_mock, patch.object(
            agent_workflow,
            "run_suite_process",
            return_value=fake_suite_execution,
        ) as run_suite_mock:
            payload, exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={
                    "target_account": "13700000000",
                    "backup_dir": "/tmp/backup-001",
                },
                allow_apply=True,
                execute_mode="preview",
                root_dir=workflow_root,
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("READY", payload["overall"])
        self.assertEqual(5, payload["summary"]["PASS"])
        self.assertEqual(2, payload["summary"]["SKIP"])
        precondition_map = {item["id"]: item for item in payload["precondition_results"]}
        self.assertEqual("PASS", precondition_map["admin-session-ready"]["status"])
        self.assertEqual("PASS", precondition_map["target-account-exists"]["status"])
        self.assertEqual("PASS", payload["step_results"][0]["status"])
        self.assertEqual("command", payload["step_results"][0]["executor"])
        self.assertEqual("unittest", payload["step_results"][2]["executor"])
        self.assertEqual("SKIP", payload["step_results"][3]["status"])
        self.assertEqual("SKIP", payload["step_results"][4]["status"])
        self.assertEqual(3, execute_step_mock.call_count)
        self.assertEqual(0, run_suite_mock.call_count)

    def test_agent_workflow_blocks_when_ownership_target_account_missing(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-ownership"
        (workflow_root / "data" / "auth").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / ".env.local").write_text("ADMIN_PHONE_NUMBERS=13711111111\n", encoding="utf-8")
        self._make_sqlite_db(
            workflow_root / "data" / "auth" / "users.db",
            ["CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, phone TEXT, created_at TEXT)"],
            [("INSERT INTO users(id, email, phone, created_at) VALUES (?, ?, ?, ?)", (1, "", "13711111111", "2026-04-07T00:00:00Z"))],
        )
        profile = agent_profiles.get_task_profile("ownership-migration")

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={"target_account": "13700000000"},
            allow_apply=False,
            execute_mode="preview",
            root_dir=workflow_root,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("ATTENTION_REQUIRED", payload["overall"])
        precondition_map = {item["id"]: item for item in payload["precondition_results"]}
        self.assertEqual("PASS", precondition_map["admin-session-ready"]["status"])
        self.assertEqual("BLOCKED", precondition_map["target-account-exists"]["status"])
        self.assertIn("目标账号不存在", precondition_map["target-account-exists"]["detail"])
        self.assertTrue(all(item["status"] == "SKIP" for item in payload["step_results"]))

    def test_agent_workflow_blocks_when_cloud_import_source_dir_missing(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-cloud-import"
        (workflow_root / "data" / "auth").mkdir(parents=True, exist_ok=True)
        self._make_sqlite_db(
            workflow_root / "data" / "auth" / "users.db",
            ["CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, phone TEXT, created_at TEXT)"],
            [("INSERT INTO users(id, email, phone, created_at) VALUES (?, ?, ?, ?)", (9, "", "13722222222", "2026-04-07T00:00:00Z"))],
        )
        profile = agent_profiles.get_task_profile("cloud-import")

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={"source_data_dir": str(workflow_root / "missing-source"), "target_user_id": "9"},
            allow_apply=False,
            execute_mode="preview",
            root_dir=workflow_root,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("ATTENTION_REQUIRED", payload["overall"])
        self.assertEqual("BLOCKED", payload["precondition_results"][0]["status"])
        self.assertIn("路径不存在", payload["precondition_results"][0]["detail"])
        self.assertEqual("PASS", payload["precondition_results"][1]["status"])

    def test_agent_workflow_blocks_when_config_center_has_no_active_license(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-config-center"
        (workflow_root / "data" / "auth").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / ".env.local").write_text("ADMIN_PHONE_NUMBERS=13900000000\n", encoding="utf-8")
        self._make_sqlite_db(
            workflow_root / "data" / "auth" / "licenses.db",
            ["CREATE TABLE licenses (id INTEGER PRIMARY KEY, status TEXT, bound_user_id INTEGER)"],
            [("INSERT INTO licenses(id, status, bound_user_id) VALUES (?, ?, ?)", (1, "revoked", None))],
        )
        profile = agent_profiles.get_task_profile("config-center")

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={},
            allow_apply=False,
            execute_mode="preview",
            root_dir=workflow_root,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("ATTENTION_REQUIRED", payload["overall"])
        precondition_map = {item["id"]: item for item in payload["precondition_results"]}
        self.assertEqual("PASS", precondition_map["admin-session-ready"]["status"])
        self.assertEqual("BLOCKED", precondition_map["active-license-exists"]["status"])
        self.assertIn("未找到活跃 License", precondition_map["active-license-exists"]["detail"])

    def test_agent_workflow_blocks_when_admin_session_whitelist_missing(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-admin-missing"
        workflow_root.mkdir(parents=True, exist_ok=True)
        profile = {
            "name": "admin-task",
            "description": "验证管理员会话前置条件",
            "risk_level": "high",
            "docs": [],
            "workflow": {
                "mode": "preview_first",
                "preconditions": [
                    {
                        "id": "admin-session-ready",
                        "title": "确认管理员白名单已配置",
                        "type": "requires_admin_session",
                        "auth_db": "data/auth/users.db",
                    }
                ],
                "steps": [{"id": "inspect", "title": "检查", "command": "echo inspect"}],
            },
        }

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={},
            allow_apply=False,
            execute_mode="preview",
            root_dir=workflow_root,
        )

        self.assertEqual(1, exit_code)
        self.assertEqual("ATTENTION_REQUIRED", payload["overall"])
        self.assertEqual("BLOCKED", payload["precondition_results"][0]["status"])
        self.assertIn("管理员白名单", payload["precondition_results"][0]["detail"])

    def test_agent_workflow_passes_when_admin_account_is_whitelisted(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-admin-pass"
        (workflow_root / "data" / "auth").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / ".env.local").write_text("ADMIN_PHONE_NUMBERS=13800000000\n", encoding="utf-8")
        self._make_sqlite_db(
            workflow_root / "data" / "auth" / "users.db",
            ["CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, phone TEXT, created_at TEXT)"],
            [("INSERT INTO users(id, email, phone, created_at) VALUES (?, ?, ?, ?)", (3, "", "13800000000", "2026-04-07T00:00:00Z"))],
        )
        profile = {
            "name": "admin-account-task",
            "description": "验证管理员账号前置条件",
            "risk_level": "high",
            "docs": [],
            "workflow": {
                "mode": "preview_first",
                "preconditions": [
                    {
                        "id": "admin-account-ready",
                        "title": "确认管理员账号在白名单内",
                        "type": "requires_admin_session",
                        "auth_db": "data/auth/users.db",
                        "account_var": "admin_account",
                        "requires": ["admin_account"],
                    }
                ],
                "steps": [{"id": "inspect", "title": "检查", "command": "echo inspect"}],
            },
        }

        payload, exit_code = agent_workflow.run_task_workflow(
            profile=profile,
            task_vars={"admin_account": "13800000000"},
            allow_apply=False,
            execute_mode="preview",
            root_dir=workflow_root,
        )

        self.assertEqual(0, exit_code)
        self.assertEqual("READY", payload["overall"])
        self.assertEqual("PASS", payload["precondition_results"][0]["status"])
        self.assertIn("管理员身份已就绪", payload["precondition_results"][0]["detail"])

    def test_agent_workflow_blocks_when_browser_env_missing(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-browser-missing"
        workflow_root.mkdir(parents=True, exist_ok=True)
        profile = {
            "name": "browser-task",
            "description": "验证浏览器环境前置条件",
            "risk_level": "medium",
            "docs": [],
            "workflow": {
                "mode": "verify_first",
                "preconditions": [
                    {
                        "id": "browser-env-ready",
                        "title": "确认浏览器环境就绪",
                        "type": "requires_browser_env",
                        "suite": "extended",
                    }
                ],
                "steps": [{"id": "inspect", "title": "检查", "command": "echo inspect"}],
            },
        }

        with patch.object(
            agent_workflow.agent_browser_smoke,
            "_dependency_summary",
            return_value={
                "node_available": True,
                "npm_available": True,
                "uv_available": True,
                "playwright_package_installed": False,
                "runner_exists": True,
            },
        ):
            payload, exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={},
                allow_apply=False,
                execute_mode="preview",
                root_dir=workflow_root,
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("ATTENTION_REQUIRED", payload["overall"])
        self.assertEqual("BLOCKED", payload["precondition_results"][0]["status"])
        self.assertIn("playwright package", payload["precondition_results"][0]["detail"])

    def test_agent_workflow_passes_when_live_backend_ready(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-live-pass"
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / "server.py").write_text("print('ok')\n", encoding="utf-8")
        (workflow_root / "web" / ".env.local").write_text("SECRET_KEY=test\n", encoding="utf-8")
        profile = {
            "name": "live-task",
            "description": "验证 live backend 前置条件",
            "risk_level": "medium",
            "docs": [],
            "workflow": {
                "mode": "verify_first",
                "preconditions": [
                    {
                        "id": "live-backend-ready",
                        "title": "确认 live backend 环境就绪",
                        "type": "requires_live_backend",
                        "suite": "live-minimal",
                        "server_path": "web/server.py",
                        "require_env_file": True
                    }
                ],
                "steps": [{"id": "inspect", "title": "检查", "command": "echo inspect"}],
            },
        }

        with patch.object(agent_workflow.shutil, "which", return_value="/usr/bin/uv"):
            payload, exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={},
                allow_apply=False,
                execute_mode="preview",
                root_dir=workflow_root,
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("READY", payload["overall"])
        self.assertEqual("PASS", payload["precondition_results"][0]["status"])
        self.assertIn("live backend 环境就绪", payload["precondition_results"][0]["detail"])

    def test_agent_workflow_blocks_when_live_backend_missing_uv(self):
        workflow_root = self.sandbox_root / "workflow-preconditions-live-blocked"
        (workflow_root / "web").mkdir(parents=True, exist_ok=True)
        (workflow_root / "web" / "server.py").write_text("print('ok')\n", encoding="utf-8")
        profile = {
            "name": "live-task-blocked",
            "description": "验证 live backend 缺少 uv",
            "risk_level": "medium",
            "docs": [],
            "workflow": {
                "mode": "verify_first",
                "preconditions": [
                    {
                        "id": "live-backend-ready",
                        "title": "确认 live backend 环境就绪",
                        "type": "requires_live_backend",
                        "suite": "live-minimal",
                        "server_path": "web/server.py"
                    }
                ],
                "steps": [{"id": "inspect", "title": "检查", "command": "echo inspect"}],
            },
        }

        with patch.object(agent_workflow.shutil, "which", return_value=None):
            payload, exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={},
                allow_apply=False,
                execute_mode="preview",
                root_dir=workflow_root,
            )

        self.assertEqual(1, exit_code)
        self.assertEqual("ATTENTION_REQUIRED", payload["overall"])
        self.assertEqual("BLOCKED", payload["precondition_results"][0]["status"])
        self.assertIn("uv", payload["precondition_results"][0]["detail"])

    def test_agent_workflow_full_requires_confirmation_and_backup_dir(self):
        workflow_root = self.sandbox_root / "workflow-dsl"
        workflow_root.mkdir(parents=True, exist_ok=True)
        backup_dir = workflow_root / "backup-001"
        backup_dir.mkdir(parents=True, exist_ok=True)
        profile = {
            "name": "danger-task",
            "description": "测试更强 workflow DSL 语义",
            "risk_level": "high",
            "docs": ["docs/agent/admin-ops.md"],
            "workflow": {
                "mode": "preview_first",
                "governance": {
                    "required_for_apply": True,
                    "fields": [
                        {"name": "change_reason", "label": "变更原因", "required": True},
                        {"name": "operator", "label": "操作者", "required": True},
                        {"name": "approver", "label": "审批人", "required": True},
                        {"name": "ticket", "label": "关联工单", "required": True},
                    ],
                },
                "steps": [
                    {
                        "id": "preview",
                        "title": "预演",
                        "command": "echo preview",
                        "produces_artifact": "artifacts/workflow/preview.json",
                    },
                    {
                        "id": "apply",
                        "title": "正式执行",
                        "command": "echo apply",
                        "requires_apply": True,
                        "confirmation_token": "DANGER_APPLY",
                        "produces_artifact": "artifacts/workflow/apply.json",
                    },
                    {
                        "id": "rollback",
                        "title": "回滚",
                        "command": "echo rollback",
                        "requires_apply": True,
                        "requires_backup": True,
                        "rollback_of": "apply",
                    },
                ],
            },
        }

        def fake_execute(step, *, root_dir):
            artifact_specs = step.get("produces_artifact") or []
            if isinstance(artifact_specs, str):
                artifact_specs = [artifact_specs]
            for artifact in artifact_specs:
                artifact_path = Path(root_dir) / artifact
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text("{}", encoding="utf-8")
            return {
                "returncode": 0,
                "stdout": "OK\n",
                "stderr": "",
                "duration_ms": 12.0,
                "highlights": ["OK"],
            }

        with patch.object(agent_workflow, "_execute_step", side_effect=fake_execute):
            blocked_payload, blocked_exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={},
                allow_apply=True,
                execute_mode="full",
                root_dir=workflow_root,
            )
            ready_payload, ready_exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={
                    "change_reason": "验证高风险治理字段",
                    "operator": "ops-bot",
                    "approver": "alice",
                    "ticket": "OPS-42",
                    "confirmation_token": "DANGER_APPLY",
                    "backup_dir": str(backup_dir),
                },
                allow_apply=True,
                execute_mode="full",
                root_dir=workflow_root,
            )

        self.assertEqual(1, blocked_exit_code)
        self.assertEqual("ATTENTION_REQUIRED", blocked_payload["overall"])
        self.assertEqual("PASS", blocked_payload["step_results"][0]["status"])
        self.assertEqual("BLOCKED", blocked_payload["step_results"][1]["status"])
        self.assertIn("change_reason", blocked_payload["step_results"][1]["detail"])
        self.assertEqual(["change_reason", "operator", "approver", "ticket"], blocked_payload["governance"]["missing_fields"])
        self.assertEqual("SKIP", blocked_payload["step_results"][2]["status"])

        self.assertEqual(0, ready_exit_code)
        self.assertEqual("READY", ready_payload["overall"])
        self.assertEqual("PASS", ready_payload["step_results"][1]["status"])
        self.assertTrue(ready_payload["step_results"][1]["artifact_paths"])
        self.assertEqual(str(backup_dir), ready_payload["step_results"][2]["backup_dir"])
        self.assertEqual("apply", ready_payload["step_results"][2]["rollback_of"])
        self.assertTrue(ready_payload["governance"]["ready"])
        self.assertEqual("OPS-42", ready_payload["governance"]["values"]["ticket"])
        self.assertIn("governance=operator=ops-bot approver=alice ticket=OPS-42", ready_payload["step_results"][1]["detail"])

    def test_agent_artifacts_handoff_includes_workflow_governance(self):
        plan_payload = agent_plans.get_plan("ownership-migration")
        summary_payload = {
            "overall": "READY_WITH_WARNINGS",
            "task": {
                "name": "ownership-migration",
                "risk_level": "high",
                "workflow_mode": "preview_first",
                "docs": ["docs/agent/migration.md"],
                "plan": plan_payload,
                "contract": agent_contracts.get_contract("ownership-migration"),
            },
            "results": [
                {
                    "name": "workflow",
                    "status": "WARN",
                    "detail": "waiting for apply governance",
                    "command": "python3 scripts/agent_harness.py --task ownership-migration",
                    "highlights": [],
                }
            ],
        }
        workflow_payload = {
            "plan": plan_payload,
            "contract": agent_contracts.get_contract("ownership-migration"),
            "workflow": {
                "docs": ["docs/agent/admin-ops.md"],
                "missing_vars": [],
                "hidden_apply_steps": [],
                "steps": [
                    {
                        "id": "apply",
                        "title": "正式落盘迁移",
                        "command": "python3 scripts/admin_migrate_ownership.py migrate --apply",
                        "requires_apply": True,
                        "confirmation_token": "OWNERSHIP_MIGRATION_APPLY",
                    }
                ],
                "governance": {
                    "required_for_apply": True,
                    "fields": [
                        {"name": "change_reason", "label": "变更原因", "required": True, "value": "修正历史归属"},
                        {"name": "operator", "label": "操作者", "required": True, "value": "ops-bot"},
                        {"name": "approver", "label": "审批人", "required": True, "value": "alice"},
                        {"name": "ticket", "label": "关联工单", "required": True, "value": "OPS-42"},
                    ],
                    "missing_fields": [],
                    "values": {
                        "change_reason": "修正历史归属",
                        "operator": "ops-bot",
                        "approver": "alice",
                        "ticket": "OPS-42",
                    },
                    "ready": True,
                },
            },
            "governance": {
                "required_for_apply": True,
                "fields": [
                    {"name": "change_reason", "label": "变更原因", "required": True, "value": "修正历史归属"},
                    {"name": "operator", "label": "操作者", "required": True, "value": "ops-bot"},
                    {"name": "approver", "label": "审批人", "required": True, "value": "alice"},
                    {"name": "ticket", "label": "关联工单", "required": True, "value": "OPS-42"},
                ],
                "missing_fields": [],
                "values": {
                    "change_reason": "修正历史归属",
                    "operator": "ops-bot",
                    "approver": "alice",
                    "ticket": "OPS-42",
                },
                "ready": True,
            },
            "precondition_results": [],
            "step_results": [
                {
                    "title": "正式落盘迁移",
                    "status": "MANUAL",
                    "detail": "人工确认后执行",
                    "command": "python3 scripts/admin_migrate_ownership.py migrate --apply",
                    "confirmation_token_hint": "OWNERSHIP_MIGRATION_APPLY",
                    "artifact_paths": [],
                }
            ],
        }
        run_dir = self.sandbox_root / "handoff-governance" / "20260408T000000Z-pid1"
        base_dir = run_dir.parent
        run_dir.mkdir(parents=True, exist_ok=True)
        handoff = agent_artifacts.build_harness_handoff_payload(
            summary_payload,
            {"generated_at": "2026-04-08T00:00:00Z", "run_dir": str(run_dir)},
            {"workflow": {"workflow": workflow_payload}},
            run_dir=run_dir,
            base_path=base_dir,
        )
        self.assertTrue(handoff["governance"]["ready"])
        self.assertEqual("ownership-migration", handoff["plan"]["task"])
        self.assertEqual("ownership-migration", handoff["contract"]["name"])
        self.assertTrue(any("docs/agent/plans/README.md" == item for item in handoff["docs"]))
        self.assertTrue(any("resources/harness/contracts/ownership-migration.json" == item for item in handoff["docs"]))
        self.assertEqual("OPS-42", handoff["governance"]["values"]["ticket"])
        self.assertTrue(any("治理记录已准备" in item for item in handoff["next_steps"]))
        self.assertTrue(
            any("python3 scripts/agent_planner.py --task ownership-migration" in item for item in handoff["resume_commands"])
            or any("优先回看 Planner Artifact" in item for item in handoff["next_steps"])
        )

    def test_agent_workflow_fails_when_declared_artifact_missing(self):
        workflow_root = self.sandbox_root / "workflow-artifact-missing"
        workflow_root.mkdir(parents=True, exist_ok=True)
        profile = {
            "name": "artifact-task",
            "description": "验证 produces_artifact 约束",
            "risk_level": "medium",
            "docs": [],
            "workflow": {
                "mode": "verify_first",
                "steps": [
                    {
                        "id": "verify",
                        "title": "执行但不落工件",
                        "command": "echo verify",
                        "produces_artifact": "artifacts/workflow/missing.json",
                    }
                ],
            },
        }

        with patch.object(
            agent_workflow,
            "_execute_step",
            return_value={
                "returncode": 0,
                "stdout": "OK\n",
                "stderr": "",
                "duration_ms": 5.0,
                "highlights": ["OK"],
            },
        ):
            payload, exit_code = agent_workflow.run_task_workflow(
                profile=profile,
                task_vars={},
                allow_apply=False,
                execute_mode="preview",
                root_dir=workflow_root,
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("BLOCKED", payload["overall"])
        self.assertEqual("FAIL", payload["step_results"][0]["status"])
        self.assertIn("未产出工件", payload["step_results"][0]["detail"])

    def test_agent_harness_can_execute_workflow_preview_steps(self):
        observed_profiles = []

        def fake_doctor_stage(**kwargs):
            observed_profiles.append(kwargs["profile"])
            return self._make_harness_execution(
                name="doctor",
                status="PASS",
                exit_code=0,
                detail="doctor ok",
            )

        workflow_payload = {
            "task": "ownership-migration",
            "description": "管理员归属迁移",
            "risk_level": "high",
            "execute_mode": "preview",
            "allow_apply": False,
            "continue_on_failure": False,
            "overall": "READY",
            "summary": {"PASS": 3, "FAIL": 0, "BLOCKED": 0, "MANUAL": 0, "PLANNED": 0, "SKIP": 0},
            "workflow": {
                "task": "ownership-migration",
                "description": "管理员归属迁移",
                "risk_level": "high",
                "workflow_mode": "preview_first",
                "docs": ["docs/agent/migration.md"],
                "steps": [
                    {
                        "id": "audit",
                        "title": "审计目标账号当前归属",
                        "command": "python3 scripts/admin_migrate_ownership.py audit --user-account 13700000000 --kinds sessions,reports",
                        "missing_vars": [],
                    }
                ],
                "hidden_apply_steps": [{"id": "apply"}],
                "missing_vars": [],
                "task_vars": {"target_account": "13700000000"},
            },
            "step_results": [
                {
                    "id": "audit",
                    "title": "审计目标账号当前归属",
                    "status": "PASS",
                    "detail": "执行成功，用时 10.00ms",
                    "command": "python3 scripts/admin_migrate_ownership.py audit --user-account 13700000000 --kinds sessions,reports",
                    "highlights": ["OK"],
                }
            ],
        }

        with patch.object(agent_harness, "run_doctor_stage", side_effect=fake_doctor_stage), patch.object(
            agent_harness.agent_workflow,
            "run_task_workflow",
            return_value=(workflow_payload, 0),
        ), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=self._make_harness_execution(name="static_guardrails", status="PASS", exit_code=0, detail="static ok"),
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=[
                self._make_harness_execution(name="guardrails", status="PASS", exit_code=0, detail="guardrails ok"),
                self._make_harness_execution(name="smoke", status="PASS", exit_code=0, detail="smoke ok"),
            ],
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(
                    [
                        "--task",
                        "ownership-migration",
                        "--task-var",
                        "target_account=13700000000",
                        "--workflow-execute",
                        "preview",
                        "--json",
                    ]
                )

        self.assertEqual(0, exit_code)
        self.assertEqual(["auto"], observed_profiles)
        payload = json.loads(stdout.getvalue())
        workflow_result = next(item for item in payload["results"] if item["name"] == "workflow")
        self.assertEqual("PASS", workflow_result["status"])
        self.assertIn("execute=preview", workflow_result["detail"])
        self.assertIn("pass=3", workflow_result["detail"])
        self.assertTrue(any("PASS 审计目标账号当前归属" in line for line in workflow_result["highlights"]))

    def test_agent_harness_marks_attention_required_workflow_as_warn(self):
        profile = agent_profiles.get_task_profile("ownership-migration")
        workflow_payload = {
            "overall": "ATTENTION_REQUIRED",
            "summary": {"PASS": 1, "FAIL": 0, "BLOCKED": 1, "MANUAL": 0, "PLANNED": 0, "SKIP": 0},
            "workflow": {
                "task": "ownership-migration",
                "description": "管理员归属迁移",
                "risk_level": "high",
                "workflow_mode": "preview_first",
                "docs": ["docs/agent/migration.md"],
                "steps": [],
                "hidden_apply_steps": [],
                "missing_vars": [],
                "task_vars": {"target_account": "13700000000"},
            },
            "step_results": [
                {
                    "id": "apply",
                    "title": "正式落盘迁移",
                    "status": "BLOCKED",
                    "detail": "需要确认词: OWNERSHIP_MIGRATION_APPLY",
                    "command": "python3 scripts/admin_migrate_ownership.py migrate --to-account 13700000000 --scope unowned --apply",
                }
            ],
        }
        with patch.object(
            agent_harness.agent_workflow,
            "run_task_workflow",
            return_value=(workflow_payload, 1),
        ):
            execution = agent_harness.build_workflow_stage(
                profile=profile,
                task_vars={"target_account": "13700000000"},
                allow_apply=True,
                execute_mode="full",
                continue_on_failure=False,
            )
        self.assertEqual("workflow", execution.result.name)
        self.assertEqual("WARN", execution.result.status)
        self.assertIn("BLOCKED 正式落盘迁移", "\n".join(execution.result.highlights))

    def test_agent_harness_writes_artifacts_and_latest_pointer(self):
        artifact_root = self.sandbox_root / "harness-artifacts"
        fake_doctor = self._make_harness_execution(
            name="doctor",
            status="PASS",
            detail="doctor ok",
            command="python3 scripts/agent_doctor.py --profile auto",
            artifact_payload={
                "name": "doctor",
                "command": "python3 scripts/agent_doctor.py --profile auto",
                "exit_code": 0,
                "payload": {"summary": {"PASS": 3, "WARN": 0, "FAIL": 0}},
            },
        )
        fake_guardrails = self._make_harness_execution(
            name="guardrails",
            status="PASS",
            detail="guardrails ok",
            command="python3 scripts/agent_guardrails.py --quiet",
            artifact_payload={
                "name": "guardrails",
                "suite": "minimal",
                "command": ["python3", "scripts/agent_guardrails.py", "--quiet"],
                "returncode": 0,
                "stdout": "OK\n",
                "stderr": "",
            },
        )
        fake_static = self._make_harness_execution(
            name="static_guardrails",
            status="PASS",
            detail="static ok",
            command="python3 scripts/agent_static_guardrails.py",
            artifact_payload={
                "name": "static_guardrails",
                "command": "python3 scripts/agent_static_guardrails.py",
                "exit_code": 0,
                "payload": {"summary": {"PASS": 8, "FAIL": 0}, "overall": "READY"},
            },
        )
        fake_smoke = self._make_harness_execution(
            name="smoke",
            status="FAIL",
            exit_code=2,
            detail="smoke failed",
            command="python3 scripts/agent_smoke.py --quiet",
            highlights=["FAIL: sample"],
            artifact_payload={
                "name": "smoke",
                "suite": "minimal",
                "command": ["python3", "scripts/agent_smoke.py", "--quiet"],
                "returncode": 1,
                "stdout": "FAIL: sample\n",
                "stderr": "Traceback\n",
            },
        )

        with patch.object(agent_harness, "run_doctor_stage", return_value=fake_doctor), patch.object(
            agent_harness,
            "run_static_guardrails_stage",
            return_value=fake_static,
        ), patch.object(
            agent_harness,
            "run_suite_stage",
            side_effect=[fake_guardrails, fake_smoke],
        ), patch.object(
            agent_harness.agent_artifacts,
            "collect_git_context",
            return_value={"commit": "abc123", "branch": "main", "is_dirty": False, "dirty_files_count": 0, "dirty_files_preview": []},
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                exit_code = agent_harness.main(["--artifact-dir", str(artifact_root), "--json"])

        self.assertEqual(2, exit_code)
        payload = json.loads(stdout.getvalue())
        self.assertEqual("BLOCKED", payload["overall"])
        artifacts = payload["artifacts"]
        run_dir = Path(artifacts["run_dir"])
        self.assertTrue(run_dir.exists())
        self.assertTrue((run_dir / "summary.json").exists())
        self.assertTrue((run_dir / "run-meta.json").exists())
        self.assertTrue((run_dir / "progress.md").exists())
        self.assertTrue((run_dir / "failure-summary.md").exists())
        self.assertTrue((run_dir / "handoff.json").exists())
        self.assertTrue((run_dir / "doctor.json").exists())
        self.assertTrue((run_dir / "static_guardrails.json").exists())
        self.assertTrue((run_dir / "guardrails.json").exists())
        self.assertTrue((run_dir / "guardrails.stdout.log").exists())
        self.assertTrue((run_dir / "smoke.stdout.log").exists())
        self.assertTrue((run_dir / "smoke.stderr.log").exists())
        self.assertTrue((artifact_root / "latest-progress.md").exists())
        self.assertTrue((artifact_root / "latest-failure-summary.md").exists())
        self.assertTrue((artifact_root / "latest-handoff.json").exists())

        latest_payload = json.loads((artifact_root / "latest.json").read_text(encoding="utf-8"))
        self.assertEqual(str(run_dir), latest_payload["run_dir"])
        self.assertEqual("BLOCKED", latest_payload["overall"])
        self.assertGreaterEqual(float(latest_payload.get("duration_ms", 0) or 0), 0.0)
        self.assertEqual(str(run_dir / "progress.md"), latest_payload["progress_file"])
        self.assertEqual(str(run_dir / "failure-summary.md"), latest_payload["failure_summary_file"])
        self.assertEqual(str(run_dir / "handoff.json"), latest_payload["handoff_file"])

        summary_payload = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual("BLOCKED", summary_payload["overall"])
        self.assertGreaterEqual(float(summary_payload.get("duration_ms", 0) or 0), 0.0)
        self.assertEqual("abc123", summary_payload["metadata"]["git"]["commit"])
        progress_md = (run_dir / "progress.md").read_text(encoding="utf-8")
        self.assertIn("Harness Progress", progress_md)
        self.assertIn("总耗时(ms)", progress_md)
        self.assertIn("`smoke`: FAIL", progress_md)
        failure_summary_md = (run_dir / "failure-summary.md").read_text(encoding="utf-8")
        self.assertIn("Harness Failure Summary", failure_summary_md)
        self.assertIn("FAIL: sample", failure_summary_md)
        self.assertIn("python3 scripts/agent_scenario_scaffold.py --source harness --run-dir", failure_summary_md)
        self.assertIn("--category ops", failure_summary_md)
        self.assertIn("--tag ops", failure_summary_md)
        self.assertIn("--output tests/harness_scenarios/ops/", failure_summary_md)
        handoff_payload = json.loads((run_dir / "handoff.json").read_text(encoding="utf-8"))
        self.assertEqual("harness", handoff_payload["kind"])
        self.assertTrue(any("smoke: smoke failed" == item for item in handoff_payload["blockers"]))
        self.assertIn("python3 scripts/agent_smoke.py --quiet", handoff_payload["resume_commands"])
        self.assertTrue(
            any(
                item.startswith("python3 scripts/agent_scenario_scaffold.py --source harness --run-dir ")
                for item in handoff_payload["resume_commands"]
            )
        )
        self.assertEqual("ops", handoff_payload["scaffold_recommendation"]["category"])
        self.assertEqual(120000, handoff_payload["scaffold_recommendation"]["budget_ms"])

    def test_cli_help_commands(self):
        commands = [
            ["python3", "scripts/agent_doctor.py", "--help"],
            ["python3", "scripts/agent_eval.py", "--help"],
            ["python3", "scripts/agent_browser_smoke.py", "--help"],
            ["python3", "scripts/agent_ci_summary.py", "--help"],
            ["python3", "scripts/agent_autodream.py", "--help"],
            ["python3", "scripts/agent_doc_gardener.py", "--help"],
            ["python3", "scripts/agent_guardrails.py", "--help"],
            ["python3", "scripts/agent_harness.py", "--help"],
            ["python3", "scripts/agent_heartbeat.py", "--help"],
            ["python3", "scripts/agent_history.py", "--help"],
            ["python3", "scripts/agent_ops.py", "--help"],
            ["python3", "scripts/agent_observe.py", "--help"],
            ["python3", "scripts/agent_playbook_sync.py", "--help"],
            ["python3", "scripts/agent_planner.py", "--help"],
            ["python3", "scripts/agent_scenario_scaffold.py", "--help"],
            ["python3", "scripts/agent_smoke.py", "--help"],
            ["python3", "scripts/agent_static_guardrails.py", "--help"],
            ["python3", "scripts/agent_workflow.py", "--help"],
            ["python3", "scripts/session_manager.py", "--help"],
            ["python3", "scripts/convert_doc.py", "--help"],
            ["python3", "scripts/report_generator.py", "--help"],
            ["python3", "scripts/migrate_session_evidence_annotations.py", "--help"],
            ["python3", "scripts/replay_preflight_diagnostics.py", "--help"],
            ["python3", "scripts/context_hub.py", "--help"],
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

        listed = subprocess.run(
            ["python3", "scripts/agent_smoke.py", "--list"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(listed.returncode, 0)
        self.assertIn("Suite: minimal", listed.stdout)
        self.assertIn("鉴权生命周期", listed.stdout)

        browser_listed = subprocess.run(
            ["python3", "scripts/agent_browser_smoke.py", "--list"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(browser_listed.returncode, 0)
        self.assertIn("Suite: minimal", browser_listed.stdout)
        self.assertIn("帮助文档静态页", browser_listed.stdout)

        guardrails_listed = subprocess.run(
            ["python3", "scripts/agent_guardrails.py", "--list"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(guardrails_listed.returncode, 0)
        self.assertIn("Suite: minimal", guardrails_listed.stdout)
        self.assertIn("匿名写接口必须被拦截", guardrails_listed.stdout)

        harness_listed = subprocess.run(
            ["python3", "scripts/agent_harness.py", "--list-stages"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(harness_listed.returncode, 0)
        self.assertIn("doctor", harness_listed.stdout)
        self.assertIn("static_guardrails", harness_listed.stdout)
        self.assertIn("guardrails", harness_listed.stdout)
        self.assertIn("smoke", harness_listed.stdout)

        static_listed = subprocess.run(
            ["python3", "scripts/agent_static_guardrails.py", "--list"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(static_listed.returncode, 0)
        self.assertIn("admin_routes_require_admin", static_listed.stdout)
        self.assertIn("public_solution_readonly", static_listed.stdout)
        self.assertIn("config_center_routes_delegate_helpers", static_listed.stdout)

        harness_observe_listed = subprocess.run(
            ["python3", "scripts/agent_harness.py", "--observe", "--list-stages"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(harness_observe_listed.returncode, 0)
        self.assertIn("observe", harness_observe_listed.stdout)

        harness_browser_listed = subprocess.run(
            ["python3", "scripts/agent_harness.py", "--browser-smoke", "--list-stages"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(harness_browser_listed.returncode, 0)
        self.assertIn("browser_smoke", harness_browser_listed.stdout)

        tasks_listed = subprocess.run(
            ["python3", "scripts/agent_harness.py", "--list-tasks"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(tasks_listed.returncode, 0)
        self.assertIn("account-merge", tasks_listed.stdout)
        self.assertIn("license-admin", tasks_listed.stdout)
        self.assertIn("license-audit", tasks_listed.stdout)
        self.assertIn("ownership-migration", tasks_listed.stdout)
        self.assertIn("cloud-import", tasks_listed.stdout)
        self.assertIn("presentation-export", tasks_listed.stdout)

    def test_scenario_loader_generates_unique_ids_within_same_second(self):
        custom_dir = self.sandbox_root / "scenario-loader" / "custom"
        builtin_dir = ROOT_DIR / "resources" / "scenarios" / "builtin"
        loader = scenario_loader.ScenarioLoader(builtin_dir=builtin_dir, custom_dir=custom_dir)

        fixed_now = scenario_loader.datetime(2026, 3, 16, 2, 5, 0)
        with patch.object(scenario_loader, "datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            scenario_id_a = loader.save_custom_scenario({
                "name": "场景A",
                "dimensions": [{"id": "d1", "name": "维度1"}],
            })
            scenario_id_b = loader.save_custom_scenario({
                "name": "场景B",
                "dimensions": [{"id": "d1", "name": "维度1"}],
            })

        self.assertNotEqual(scenario_id_a, scenario_id_b)
        self.assertTrue((custom_dir / f"{scenario_id_a}.json").exists())
        self.assertTrue((custom_dir / f"{scenario_id_b}.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
