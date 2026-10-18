"""
Unit tests for LLM client wrapper, token tracking, cost accounting, and usage reporting.
"""

from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from llm_client import (
    LLMCallRecord,
    LLMTracker,
    calculate_cost,
    track_llm_call,
    wrap_llm_call,
)


class TestLLMClient(unittest.TestCase):
    def setUp(self):
        self.tracker = LLMTracker()
        self.tracker.reset()

    def tearDown(self):
        self.tracker.reset()

    def test_record_call_attributes(self):
        """Prompt 7: Attributes logged: timestamp, model, purpose_tag, input_tokens, output_tokens, estimated_cost."""
        rec = self.tracker.record_call(
            model="claude-3-5-sonnet-20241022",
            purpose_tag="image_fact_extraction",
            input_tokens=1800,
            output_tokens=30,
        )

        # Verify all 6 mandatory attributes exist and are properly populated
        self.assertTrue(hasattr(rec, "timestamp"))
        self.assertTrue(isinstance(rec.timestamp, str))
        self.assertEqual(rec.model, "claude-3-5-sonnet-20241022")
        self.assertEqual(rec.purpose_tag, "image_fact_extraction")
        self.assertEqual(rec.input_tokens, 1800)
        self.assertEqual(rec.output_tokens, 30)
        self.assertTrue(isinstance(rec.estimated_cost, Decimal))
        self.assertGreater(rec.estimated_cost, Decimal(0))

        # Backward compatibility properties
        self.assertEqual(rec.model_name, "claude-3-5-sonnet-20241022")
        self.assertEqual(rec.purpose, "image_fact_extraction")
        self.assertEqual(rec.cost_usd, rec.estimated_cost)

    def test_cost_calculation(self):
        """Test cost calculation rates for Claude 3.5 Sonnet and other models."""
        # 1M input = $3.00, 1M output = $15.00
        cost_sonnet = calculate_cost("claude-3-5-sonnet-20241022", 1_000_000, 1_000_000)
        self.assertEqual(cost_sonnet, Decimal("18.000000"))

        # Haiku: $0.80/1M in, $4.00/1M out
        cost_haiku = calculate_cost("claude-3-5-haiku-20241022", 1_000_000, 1_000_000)
        self.assertEqual(cost_haiku, Decimal("4.800000"))

    def test_decorator_tracking(self):
        """Test @track_llm_call decorator captures invocation metrics."""
        @track_llm_call(purpose_tag="decision_explanation", model="claude-3-5-sonnet-20241022")
        def mock_llm(prompt: str):
            return "Explanation verdict", 120, 35

        result = mock_llm("test prompt")
        self.assertEqual(result, "Explanation verdict")
        self.assertEqual(len(self.tracker.records), 1)

        rec = self.tracker.records[0]
        self.assertEqual(rec.purpose_tag, "decision_explanation")
        self.assertEqual(rec.input_tokens, 120)
        self.assertEqual(rec.output_tokens, 35)
        self.assertTrue(rec.success)

    def test_usage_report_markdown_contents(self):
        """
        Prompt 7: Save evaluation/usage_report.md containing:
        - Per-model summary breakdown tables.
        - Overall aggregate usage totals.
        - Per-request average token count and cost metrics.
        """
        self.tracker.record_call(
            model="claude-3-5-sonnet-20241022",
            purpose_tag="image_fact_extraction",
            input_tokens=1800,
            output_tokens=30,
        )
        self.tracker.record_call(
            model="claude-3-5-sonnet-20241022",
            purpose_tag="decision_explanation",
            input_tokens=150,
            output_tokens=40,
        )

        md = self.tracker.generate_report_markdown(total_requests=250)

        # 1. Overall aggregate usage totals
        self.assertIn("1. Overall Aggregate Usage Totals", md)
        self.assertIn("Total Model Calls:", md)
        self.assertIn("Total Input Tokens:", md)
        self.assertIn("Total Output Tokens:", md)
        self.assertIn("Total Estimated Cost:", md)

        # 2. Per-request average token count and cost metrics
        self.assertIn("2. Per-Request Average Metrics (N = 250 requests)", md)
        self.assertIn("Average Input Tokens Per Request:", md)
        self.assertIn("Average Output Tokens Per Request:", md)
        self.assertIn("Average Total Tokens Per Request:", md)
        self.assertIn("Average Estimated Cost Per Request:", md)

        # 3. Per-model summary breakdown tables
        self.assertIn("3. Per-Model Summary Breakdown Table", md)
        self.assertIn("claude-3-5-sonnet-20241022", md)

        # 4. Purpose breakdown table
        self.assertIn("4. Purpose Breakdown Table", md)
        self.assertIn("image_fact_extraction", md)
        self.assertIn("decision_explanation", md)

    def test_write_usage_report_file(self):
        """Verify writing report creates file and directories correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "evaluation" / "usage_report.md"
            self.tracker.record_call(
                model="claude-3-5-sonnet-20241022",
                purpose_tag="image_fact_extraction",
                input_tokens=1000,
                output_tokens=25,
            )
            self.tracker.write_usage_report(out_file, total_requests=250)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("LLM Token & Cost Accounting Report", content)
            self.assertIn("Per-Request Average Metrics", content)

    def test_packaged_code_zip_has_usage_report(self):
        """Verify code.zip contains evaluation/usage_report.md at root of zip."""
        import zipfile
        repo_root = code_dir.parent
        zip_file = repo_root / "code.zip"
        if zip_file.exists():
            with zipfile.ZipFile(zip_file, "r") as zf:
                names = zf.namelist()
                self.assertIn("evaluation/usage_report.md", names)
                self.assertIn("run.py", names)
                self.assertIn("code/main.py", names)


if __name__ == "__main__":
    unittest.main()
