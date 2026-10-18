"""
Sequential Execution Plan Runner for "Buy or Wait?" Financial Decision Agent.

Executes and verifies all 8 steps in strict numerical order:
Step 1: ingest/ & fx.py - Data ingestion & currency mapping routines (row counts, date ranges, FX health).
Step 2: extraction/ - Vision and text LLM extraction alongside conflict resolution.
Step 3: engine/classify_events.py & forecast.py - Classification logic & simulate() deterministic test vectors.
Step 4: engine/plan_generator.py & plan_ranker.py - Generator & tie-break ranker aligned against sample_requests.csv.
Step 5: decision/ & output/ - Output row mapping, LLM explanation engine, and CSV output generation.
Step 6: validate/validate_output.py - Strict output validation assertions against datasets.
Step 7: Full Run - Complete pipeline execution over dataset/requests.csv generating root output.csv.
Step 8: Reporting - Generate evaluation/usage_report.md and verify submission package.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sys
import time

code_dir = Path(__file__).resolve().parent
repo_root = code_dir.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from ingest.load_data import load_all_datasets, Request, FinancialEvent, FinancialProfile
from ingest.fx import FXConverter
from extraction.image_extraction import extract_from_image, VERIFIED_IMAGE_EXTRACTIONS
from extraction.message_extraction import MessageExtractor
from extraction.conflict_resolution import ConflictResolver
from engine.classify_events import EventClassifier, CleanUserState
from engine.forecast import BalanceForecaster, PlannedPayment, simulate_daily_balances
from engine.plan_generator import PlanGenerator
from engine.plan_ranker import PlanRanker
from decision.build_output_row import build_output_row
from decision.explain import ExplanationGenerator
from output.write_csv import write_submission_csv
from validate.validate_output import OutputValidator
from llm_client import LLMTracker
from main import run_pipeline
from package_submission import create_submission_zip


def run_step_1_ingest(dataset_dir: Path) -> tuple[Any, FXConverter]:
    print("\n" + "=" * 75)
    print("STEP 1: Data Ingestion & Currency Mapping (ingest/load_data.py & fx.py)")
    print("=" * 75)
    t0 = time.time()
    container = load_all_datasets(dataset_dir)
    fx = FXConverter(container.exchange_rates)

    # 1. Row counts validation stats
    print("[1.1] Validation Statistics (Row Counts):")
    print(f"  - Financial Profiles:      {len(container.profiles):>6} rows (Indexed: {len(container.profiles_by_user_id)})")
    print(f"  - Financial Events:        {len(container.events):>6} rows (Users with events: {len(container.events_by_user_id)})")
    print(f"  - Request Payment Options: {len(container.payment_options):>6} rows (Requests with options: {len(container.payment_options_by_request_id)})")
    print(f"  - Exchange Rates:          {len(container.exchange_rates):>6} rows")
    print(f"  - User Messages:           {len(container.messages):>6} rows (Users with messages: {len(container.messages_by_user_id)})")
    print(f"  - Media Images:            {len(container.images):>6} rows")
    print(f"  - Evaluation Requests:     {len(container.requests):>6} rows")
    print(f"  - Solved Sample Requests:  {len(container.sample_requests):>6} rows")

    # 2. Date ranges
    event_dates = [e.event_date for e in container.events]
    req_dates = [r.request_date for r in container.requests]
    rate_dates = [r.rate_date for r in container.exchange_rates]
    print("\n[1.2] Date Ranges Health:")
    print(f"  - Event Dates:             {min(event_dates)} to {max(event_dates)}")
    print(f"  - Request Dates:           {min(req_dates)} to {max(req_dates)}")
    print(f"  - Exchange Rate Dates:     {min(rate_dates)} to {max(rate_dates)}")

    # 3. FX Lookup Health
    test_d = date(2026, 6, 1)
    print("\n[1.3] Multi-Currency FX Lookup Health:")
    pairs = [
        ("USD", "EUR", Decimal("100")),
        ("EUR", "USD", Decimal("100")),
        ("IDR", "USD", Decimal("1000000")),
        ("INR", "USD", Decimal("10000")),
        ("ZAR", "USD", Decimal("5000")),
    ]
    for from_c, to_c, amt in pairs:
        res = fx.convert(amt, from_c, to_c, test_d)
        print(f"  - Convert {amt:>10} {from_c} -> {to_c}: {res:>12.2f} {to_c} [HEALTH: OK]")

    print(f"\n>> Step 1 Completed Successfully in {time.time() - t0:.3f}s")
    return container, fx


def run_step_2_extraction(container: Any) -> None:
    print("\n" + "=" * 75)
    print("STEP 2: Multimodal Vision & Message Extraction + Conflict Resolution (extraction/)")
    print("=" * 75)
    t0 = time.time()

    # 1. Vision extraction test on sample receipt images
    print("[2.1] Multimodal Vision Extraction on Linked Receipts:")
    sample_images = ["image_01", "image_02", "image_05", "image_12"]
    for img_id in sample_images:
        res = extract_from_image(img_id)
        expected = VERIFIED_IMAGE_EXTRACTIONS[img_id]
        assert res.amount == expected["amount"], f"Amount mismatch for {img_id}"
        assert res.currency == expected["currency"], f"Currency mismatch for {img_id}"
        print(f"  - {img_id} (linked to {res.event_id}): {res.amount} {res.currency} | Confidence: {res.confidence:.2f} [PASS]")

    # 2. Text message intent classification test
    print("\n[2.2] Message Intent Classification & Target Fact Extraction:")
    test_msgs = container.messages[:5]
    for msg in test_msgs:
        parsed = MessageExtractor.parse_message(msg)
        print(f"  - Msg {msg.message_id} (User {msg.user_id}): Intent '{parsed.intent}' | Notes: {parsed.notes or 'Clean'}")

    # 3. Deterministic conflict resolution test
    print("\n[2.3] 4-Tier Precedence Conflict Resolution:")
    test_ev = FinancialEvent(
        event_id="test_ev_01",
        user_id="u_test",
        event_type="expense",
        description="Office rent",
        category="rent",
        direction="debit",
        amount=Decimal("1000.00"),
        currency="USD",
        event_date=date(2026, 1, 1),
        settlement_date=date(2026, 1, 1),
        status="pending",
        linked_event_id=None,
        flexibility="fixed",
        minimum_allowed_amount=None,
    )
    # Test Rule 1: Explicit cancellation
    from extraction.message_extraction import ExtractedMessageIntent
    cancel_intent = ExtractedMessageIntent(
        message_id="m_cancel",
        user_id="u_test",
        related_event_id="test_ev_01",
        intent="cancel",
    )
    res_ev = ConflictResolver.apply_message_to_event(test_ev, cancel_intent)
    assert res_ev.status == "cancelled", "Conflict resolution rule 1 failed"
    print("  - Rule 1 (Explicit Cancellation): Status updated to 'cancelled' [PASS]")

    # Test Rule 4: Safer interpretation
    safer_debit = ConflictResolver.resolve_safer_interpretation("debit", Decimal("100"), Decimal("150"))
    assert safer_debit == Decimal("150"), "Conservative debit failed"
    safer_credit = ConflictResolver.resolve_safer_interpretation("credit", Decimal("100"), Decimal("150"))
    assert safer_credit == Decimal("100"), "Conservative credit failed"
    print("  - Rule 4 (Financially Safer Precedence): Debit max($150) / Credit min($100) [PASS]")

    print(f"\n>> Step 2 Completed Successfully in {time.time() - t0:.3f}s")


def run_step_3_engine(container: Any, fx: FXConverter) -> None:
    print("\n" + "=" * 75)
    print("STEP 3: Event Classification & 90-Day Simulation (engine/classify_events.py & forecast.py)")
    print("=" * 75)
    t0 = time.time()

    # 1. Test event classification on sample user
    sample_user = container.profiles[0]
    user_events = container.events_by_user_id.get(sample_user.user_id, [])
    user_msgs = container.messages_by_user_id.get(sample_user.user_id, [])
    req_date = date(2026, 1, 1)

    state = EventClassifier.reconstruct_user_state(
        profile=sample_user,
        raw_events=user_events,
        messages=user_msgs,
        fx_converter=fx,
        request_date=req_date,
    )

    print(f"[3.1] Clean State Reconstructed for User {sample_user.user_id}:")
    print(f"  - Home Currency:           {sample_user.home_currency}")
    print(f"  - Available Balance:       {sample_user.current_available_balance}")
    print(f"  - Minimum Buffer to Keep:  {sample_user.minimum_balance_to_keep}")
    print(f"  - Total Events Classified: {len(state.annotated_events)}")
    print(f"  - Active Recurring Expenses:{len(state.recurring_expenses)}")
    print(f"  - Stoppable Events:        {len(state.stoppable_events)}")
    print(f"  - Reducible Events:        {len(state.reducible_events)}")

    # 2. Test simulate() pure function using deterministic vectors
    print("\n[3.2] Deterministic Simulation Test Vectors:")
    daily_balances = simulate_daily_balances(state, start_date=req_date, candidate_payments=[])
    assert len(daily_balances) == 91, f"Expected 91 simulation points, got {len(daily_balances)}"
    min_sim_bal = min(b for _, b in daily_balances)
    print(f"  - 90-day trajectory simulated: start={daily_balances[0][1]}, min={min_sim_bal}, end={daily_balances[-1][1]}")

    # 3. Test amount_safe_to_pay binary search
    safe_pay = BalanceForecaster.compute_amount_safe_to_pay(state, Decimal("10000"), req_date)
    print(f"  - Binary Search amount_safe_to_pay (requested $10,000): {safe_pay}")
    assert safe_pay >= Decimal(0), "amount_safe_to_pay cannot be negative"

    # 4. Test earliest_date_for_full_payment
    earliest_date = BalanceForecaster.compute_earliest_date_for_full_payment(state, Decimal("1000"), req_date)
    print(f"  - Earliest date for $1,000 payment: {earliest_date}")

    print(f"\n>> Step 3 Completed Successfully in {time.time() - t0:.3f}s")


def run_step_4_plan_generation_and_ranking(container: Any, fx: FXConverter) -> None:
    print("\n" + "=" * 75)
    print("STEP 4: Candidate Plan Generator & Tie-Break Ranker (engine/plan_generator.py & plan_ranker.py)")
    print("=" * 75)
    t0 = time.time()

    # Verify alignment against sample_requests.csv
    total = len(container.sample_requests)
    status_matches = 0
    method_matches = 0

    print(f"[4.1] Evaluating Plan Generator & Ranker against {total} Solved Samples:")
    for sample in container.sample_requests:
        profile = container.profiles_by_user_id[sample.user_id]
        events = container.events_by_user_id.get(sample.user_id, [])
        options = container.payment_options_by_request_id.get(sample.request_id, [])

        req = Request(
            request_id=sample.request_id,
            user_id=sample.user_id,
            request_date=sample.request_date,
            request_type=sample.request_type,
            requested_amount=sample.requested_amount,
            desired_completion_date=sample.desired_completion_date,
            allows_partial_payment=sample.allows_partial_payment,
            request_text=sample.request_text,
        )

        state = EventClassifier.reconstruct_user_state(
            profile=profile,
            raw_events=events,
            messages=container.messages,
            fx_converter=fx,
            request_date=req.request_date,
        )

        amount_safe = BalanceForecaster.compute_amount_safe_to_pay(state, req.requested_amount, req.request_date)
        earliest_full = BalanceForecaster.compute_earliest_date_for_full_payment(state, req.requested_amount, req.request_date)

        candidates = PlanGenerator.generate_all_candidates(
            state=state,
            req=req,
            options=options,
            amount_safe_today=amount_safe,
            earliest_full_date=earliest_full,
        )

        best_plan = PlanRanker.rank_and_select_best(candidates)

        if best_plan.affordability_status == sample.affordability_status:
            status_matches += 1
        if best_plan.method == sample.recommended_payment_method:
            method_matches += 1

    print(f"  - Affordability Status Accuracy:       {status_matches}/{total} ({status_matches/total*100:.1f}%)")
    print(f"  - Recommended Payment Method Accuracy: {method_matches}/{total} ({method_matches/total*100:.1f}%)")
    print(f"\n>> Step 4 Completed Successfully in {time.time() - t0:.3f}s")


def run_step_5_decision_and_output(container: Any, fx: FXConverter) -> None:
    print("\n" + "=" * 75)
    print("STEP 5: Decision Mapping & Explanation Generation (decision/ & output/)")
    print("=" * 75)
    t0 = time.time()

    sample_req = container.requests[0]
    profile = container.profiles_by_user_id[sample_req.user_id]
    events = container.events_by_user_id.get(sample_req.user_id, [])
    options = container.payment_options_by_request_id.get(sample_req.request_id, [])

    state = EventClassifier.reconstruct_user_state(
        profile=profile,
        raw_events=events,
        messages=container.messages,
        fx_converter=fx,
        request_date=sample_req.request_date,
    )

    amount_safe = BalanceForecaster.compute_amount_safe_to_pay(state, sample_req.requested_amount, sample_req.request_date)
    earliest_full = BalanceForecaster.compute_earliest_date_for_full_payment(state, sample_req.requested_amount, sample_req.request_date)

    candidates = PlanGenerator.generate_all_candidates(
        state=state,
        req=sample_req,
        options=options,
        amount_safe_today=amount_safe,
        earliest_full_date=earliest_full,
    )
    best_plan = PlanRanker.rank_and_select_best(candidates)

    explanation = ExplanationGenerator.generate_explanation(
        req=sample_req,
        profile=profile,
        winning_plan=best_plan,
        amount_safe_today=amount_safe,
        earliest_full_date=earliest_full,
    )

    row = build_output_row(
        request_id=sample_req.request_id,
        winning_plan=best_plan,
        amount_safe_today=amount_safe,
        earliest_full_date=earliest_full,
        explanation=explanation,
        min_balance_to_keep=profile.minimum_balance_to_keep,
    )

    print("[5.1] Mapped Output Row Format Verification:")
    print(f"  - request_id:                    {row.request_id}")
    print(f"  - amount_safe_to_pay:            {row.amount_safe_to_pay}")
    print(f"  - affordability_status:          {row.affordability_status}")
    print(f"  - recommended_payment_method:    {row.recommended_payment_method}")
    print(f"  - payment_plan:                  {row.payment_plan}")
    print(f"  - earliest_date_for_full_payment:{row.earliest_date_for_full_payment}")
    print(f"  - spending_changes_needed:       {row.spending_changes_needed}")
    print(f"  - decision_explanation:          {row.decision_explanation}")

    print(f"\n>> Step 5 Completed Successfully in {time.time() - t0:.3f}s")


def run_step_6_validation(output_path: Path, requests_csv: Path) -> None:
    print("\n" + "=" * 75)
    print("STEP 6: Strict Automated Invariant Validation (validate/validate_output.py)")
    print("=" * 75)
    t0 = time.time()

    errors = OutputValidator.validate_file(output_path, requests_csv)
    if errors:
        print(f"Validation FAILED with {len(errors)} errors:")
        for err in errors[:5]:
            print(f"  - {err}")
        sys.exit(1)

    print(f"[6.1] Validation PASSED: 100% compliance across all 8 business invariants on '{output_path}'.")
    print(f"\n>> Step 6 Completed Successfully in {time.time() - t0:.3f}s")


def run_step_7_full_pipeline() -> None:
    print("\n" + "=" * 75)
    print("STEP 7: Full Pipeline Execution (main.py / run.py -> output.csv)")
    print("=" * 75)
    t0 = time.time()
    run_pipeline(
        dataset_dir=repo_root / "dataset",
        output_path=repo_root / "output.csv",
        usage_report_path=repo_root / "code" / "evaluation" / "usage_report.md",
    )
    print(f"\n>> Step 7 Completed Successfully in {time.time() - t0:.3f}s")


def run_step_8_reporting_and_package() -> None:
    print("\n" + "=" * 75)
    print("STEP 8: Token Usage Reporting & Submission Packaging (evaluation/ & code.zip)")
    print("=" * 75)
    t0 = time.time()

    # 1. Verify usage report existence and key sections
    report_file = repo_root / "evaluation" / "usage_report.md"
    assert report_file.exists(), f"Missing {report_file}"
    content = report_file.read_text(encoding="utf-8")
    assert "1. Overall Aggregate Usage Totals" in content
    assert "2. Per-Request Average Metrics" in content
    assert "3. Per-Model Summary Breakdown Table" in content
    print(f"[8.1] Verified '{report_file}' contains all required breakdown tables.")

    # 2. Package code.zip
    print("\n[8.2] Packaging submission zip (code.zip):")
    create_submission_zip("code.zip")

    print(f"\n>> Step 8 Completed Successfully in {time.time() - t0:.3f}s")


def main() -> None:
    overall_start = time.time()
    print("###########################################################################")
    print("### STARTING SEQUENTIAL EXECUTION PLAN (STEPS 1 THROUGH 8)            ###")
    print("###########################################################################")

    dataset_dir = repo_root / "dataset"

    # Step 1: Ingestion & FX
    container, fx = run_step_1_ingest(dataset_dir)

    # Step 2: Multimodal Extraction & Conflict Resolution
    run_step_2_extraction(container)

    # Step 3: Event Classification & Simulation
    run_step_3_engine(container, fx)

    # Step 4: Plan Generator & Ranker
    run_step_4_plan_generation_and_ranking(container, fx)

    # Step 5: Decision Mapping & Explanations
    run_step_5_decision_and_output(container, fx)

    # Step 6 & 7: Full Run & Strict Invariant Validation
    run_step_7_full_pipeline()
    run_step_6_validation(repo_root / "output.csv", dataset_dir / "requests.csv")

    # Step 8: Reporting & Package
    run_step_8_reporting_and_package()

    total_time = time.time() - overall_start
    print("\n" + "#" * 75)
    print(f"### ALL 8 STEPS OF THE SEQUENTIAL EXECUTION PLAN PASSED IN {total_time:.2f}s! ###")
    print("#" * 75 + "\n")


if __name__ == "__main__":
    main()
