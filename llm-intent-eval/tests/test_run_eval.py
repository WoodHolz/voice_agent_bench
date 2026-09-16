import importlib.util
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_eval.py"
SPEC = importlib.util.spec_from_file_location("run_eval", MODULE_PATH)
assert SPEC and SPEC.loader
run_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_eval
SPEC.loader.exec_module(run_eval)


class RunEvalTests(unittest.TestCase):
    def test_resolve_endpoint_accepts_base_or_full_url(self):
        self.assertEqual(
            run_eval.resolve_endpoint("http://localhost:8000/v1"),
            "http://localhost:8000/v1/chat/completions",
        )
        self.assertEqual(
            run_eval.resolve_endpoint("http://localhost:8000/v1/chat/completions"),
            "http://localhost:8000/v1/chat/completions",
        )

    def test_render_prompt_serializes_all_fields(self):
        case_input = {
            "dialogue_state": {"stage": "opening"},
            "history": [{"role": "user", "text": "你好"}],
            "user_text": "方便",
            "candidate_sops": [{"id": "7-6"}],
        }
        template = "{{dialogue_state}}\n{{history}}\n{{user_text}}\n{{candidate_sops}}"
        rendered = run_eval.render_prompt(template, case_input)
        self.assertNotIn("{{", rendered)
        self.assertIn("方便", rendered)
        self.assertIn("7-6", rendered)

    def test_parse_output_handles_code_fence(self):
        parsed, error = run_eval.parse_output('```json\n{"sop_id":"7-6","detail":"继续主流程"}\n```')
        self.assertIsNone(error)
        self.assertEqual(parsed["sop_id"], "7-6")

    def test_score_case_checks_schema_candidates_and_gold(self):
        case = {
            "input": {"candidate_sops": [{"id": "7-6"}, {"id": "7-7"}]},
            "expected": {"acceptable_sop_ids": ["7-6"]},
        }
        score = run_eval.score_case(case, '{"sop_id":"7-6","detail":"继续主流程"}')
        self.assertTrue(score["json_valid"])
        self.assertTrue(score["candidate_valid"])
        self.assertTrue(score["sop_correct"])

    def test_profile_reads_secrets_from_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "base_url": "http://localhost:8000/v1",
                        "api_key_env": "RUN_EVAL_TEST_KEY",
                        "model": "test",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict("os.environ", {"RUN_EVAL_TEST_KEY": "secret"}):
                profile = run_eval.load_profile(path)
        self.assertEqual(profile["api_key"], "secret")


if __name__ == "__main__":
    unittest.main()
