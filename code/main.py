"""
Main solution entry point for 'Buy or Wait?' financial decision agent.

Ingests dataset, evaluates all 250 requests, produces root output.csv,
validates business invariants, and writes token/cost report.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import time

# Add code dir to sys.path
code_dir = Path(__file__).resolve().parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from ingest.load_data import load_all_datasets, Request
from ingest.fx import FXConverter
from engine.classify_events import EventClassifier
from engine.forecast import BalanceForecaster
from engine.plan_generator import PlanGenerator
from engine.plan_ranker import PlanRanker
from decision.build_output_row import build_output_row, DecisionOutcome
from decision.explain import ExplanationGenerator
from output.write_csv import write_submission_csv
from validate.validate_output import OutputValidator
from llm_client import LLMTracker


def run_pipeline(
    dataset_dir: str | Path = "dataset",
    output_path: str | Path = "output.csv",
    usage_report_path: str | Path = "code/evaluation/usage_report.md",
) -> None:
    start_time = time.time()
    print("=" * 70)
    print("Starting 'Buy or Wait?' Financial Decision Agent Pipeline")
    print("=" * 70)

    # 1. Ingest datasets
    print(f"Loading datasets from '{dataset_dir}'...")
    container = load_all_datasets(dataset_dir)
    fx = FXConverter(container.exchange_rates)
    print(f"Loaded {len(container.requests)} evaluation requests across {len(container.profiles)} user profiles.")

    # 2. Process all evaluation requests
    outcomes: list[DecisionOutcome] = []
    print("\nSimulating 90-day cash flows and ranking optimal affordability plans...")

    for i, req in enumerate(container.requests, start=1):
        profile = container.profiles_by_user_id[req.user_id]
        events = container.events_by_user_id.get(req.user_id, [])
        options = container.payment_options_by_request_id.get(req.request_id, [])

        # Reconstruct clean state
        state = EventClassifier.reconstruct_user_state(
            profile=profile,
            raw_events=events,
            messages=container.messages,
            fx_converter=fx,
            request_date=req.request_date,
        )

        # Compute safe payment today and earliest full date
        amount_safe = BalanceForecaster.compute_amount_safe_to_pay(state, req.requested_amount, req.request_date)
        earliest_full = BalanceForecaster.compute_earliest_date_for_full_payment(state, req.requested_amount, req.request_date)

        # Generate candidate plans (including counterfactuals and spending changes)
        candidates = PlanGenerator.generate_all_candidates(
            state=state,
            req=req,
            options=options,
            amount_safe_today=amount_safe,
            earliest_full_date=earliest_full,
        )

        # Rank candidates via deterministic 6-tier hierarchy
        best_plan = PlanRanker.rank_and_select_best(candidates)

        # Generate action-oriented explanation
        explanation = ExplanationGenerator.generate_explanation(
            req=req,
            profile=profile,
            winning_plan=best_plan,
            amount_safe_today=amount_safe,
            earliest_full_date=earliest_full,
        )

        # Build output row with resilience tier
        outcome = build_output_row(
            request_id=req.request_id,
            winning_plan=best_plan,
            amount_safe_today=amount_safe,
            earliest_full_date=earliest_full,
            explanation=explanation,
            min_balance_to_keep=profile.minimum_balance_to_keep,
        )
        outcomes.append(outcome)

        if i % 50 == 0 or i == len(container.requests):
            print(f"  Processed {i}/{len(container.requests)} requests ({outcome.affordability_status}, {outcome.recommended_payment_method})")

    # 3. Write output.csv in root directory
    repo_root = Path(dataset_dir).resolve().parent
    final_output_file = repo_root / "output.csv"
    print(f"\nWriting final predictions to '{final_output_file}'...")
    write_submission_csv(outcomes, final_output_file)

    # 4. Invariant validation
    print("Validating business invariants against output.csv...")
    errors = OutputValidator.validate_file(final_output_file, requests_csv_path=Path(dataset_dir) / "requests.csv")
    if errors:
        print(f"Validation FAILED with {len(errors)} errors:")
        for err in errors[:5]:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("Validation PASSED: All 250 predictions comply 100% with challenge invariants.")

    # 5. Write usage report
    print(f"Writing usage and token report to '{usage_report_path}'...")
    tracker = LLMTracker()
    tracker.write_usage_report(usage_report_path, total_requests=len(container.requests))

    elapsed = time.time() - start_time
    print("=" * 70)
    print(f"Pipeline finished successfully in {elapsed:.2f}s!")
    print("=" * 70)


if __name__ == "__main__":
    run_pipeline()
