"""
Local evaluation benchmark comparing pipeline predictions against sample_requests.csv.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import sys

# Add code dir to sys.path
code_dir = Path(__file__).resolve().parent.parent
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from ingest.load_data import load_all_datasets, Request
from ingest.fx import FXConverter
from engine.classify_events import EventClassifier
from engine.forecast import BalanceForecaster
from engine.plan_generator import PlanGenerator
from engine.plan_ranker import PlanRanker
from decision.build_output_row import build_output_row
from decision.explain import ExplanationGenerator


def evaluate_sample_requests(dataset_dir: str | Path = "dataset"):
    print("Loading datasets for local evaluation...")
    container = load_all_datasets(dataset_dir)
    fx = FXConverter(container.exchange_rates)

    total = len(container.sample_requests)
    status_matches = 0
    method_matches = 0
    amount_safe_diffs = []
    earliest_matches = 0

    print(f"\nEvaluating {total} solved sample requests against deterministic pipeline:\n")
    print(f"{'Request':<12} | {'True Status':<20} | {'Pred Status':<20} | {'Method Match':<12} | {'Safe Pay Diff'}")
    print("-" * 80)

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

        status_ok = (best_plan.affordability_status == sample.affordability_status)
        method_ok = (best_plan.method == sample.recommended_payment_method)
        if status_ok:
            status_matches += 1
        if method_ok:
            method_matches += 1

        diff = abs(amount_safe - sample.amount_safe_to_pay)
        amount_safe_diffs.append(diff)

        earliest_true = sample.earliest_date_for_full_payment
        if best_plan.affordability_status == "affordable_now":
            pred_earliest = req.request_date
        else:
            pred_earliest = earliest_full

        if pred_earliest == earliest_true:
            earliest_matches += 1

        status_flag = "PASS" if status_ok else "FAIL"
        method_flag = "PASS" if method_ok else "FAIL"
        print(f"{sample.request_id:<12} | {sample.affordability_status:<20} | {best_plan.affordability_status:<20} | {method_flag:<12} | {diff}")

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY:")
    print(f"Status Accuracy:             {status_matches}/{total} ({status_matches/total*100:.1f}%)")
    print(f"Recommended Method Accuracy: {method_matches}/{total} ({method_matches/total*100:.1f}%)")
    print(f"Earliest Date Accuracy:      {earliest_matches}/{total} ({earliest_matches/total*100:.1f}%)")
    print(f"Mean Safe Amount Diff:       {sum(amount_safe_diffs)/total:.2f}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    evaluate_sample_requests()
