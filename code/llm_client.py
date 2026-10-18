"""
LLM Client wrapper with automatic token tracking, purpose logging,
cost accounting, and usage report generation.

Prompt 7 Requirements:
- Attributes logged: timestamp, model, purpose_tag, input_tokens, output_tokens, estimated_cost.
- Save evaluation/usage_report.md at execution completion containing:
  * Per-model summary breakdown tables.
  * Overall aggregate usage totals.
  * Per-request average token count and cost metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


# Standard model pricing (USD per token): (input_cost_per_token, output_cost_per_token)
MODEL_PRICING: Dict[str, Tuple[Decimal, Decimal]] = {
    "claude-3-5-sonnet": (Decimal("0.000003"), Decimal("0.000015")),       # $3.00 / 1M in, $15.00 / 1M out
    "claude-3-sonnet": (Decimal("0.000003"), Decimal("0.000015")),
    "claude-3-5-haiku": (Decimal("0.0000008"), Decimal("0.000004")),      # $0.80 / 1M in, $4.00 / 1M out
    "claude-3-haiku": (Decimal("0.00000025"), Decimal("0.00000125")),     # $0.25 / 1M in, $1.25 / 1M out
    "claude-3-opus": (Decimal("0.000015"), Decimal("0.000075")),          # $15.00 / 1M in, $75.00 / 1M out
    "gpt-4o": (Decimal("0.0000025"), Decimal("0.000010")),                 # $2.50 / 1M in, $10.00 / 1M out
    "gpt-4o-mini": (Decimal("0.00000015"), Decimal("0.00000060")),        # $0.15 / 1M in, $0.60 / 1M out
    "default": (Decimal("0.000003"), Decimal("0.000015")),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate estimated cost in USD for a given model and token counts."""
    model_lower = model.lower()
    for prefix, (in_rate, out_rate) in MODEL_PRICING.items():
        if prefix in model_lower:
            cost = Decimal(input_tokens) * in_rate + Decimal(output_tokens) * out_rate
            return cost.quantize(Decimal("0.000001"))
    in_rate, out_rate = MODEL_PRICING["default"]
    cost = Decimal(input_tokens) * in_rate + Decimal(output_tokens) * out_rate
    return cost.quantize(Decimal("0.000001"))


@dataclass
class LLMCallRecord:
    """
    Structured record of an LLM call capturing mandatory audit metrics.
    Attributes logged: timestamp, model, purpose_tag, input_tokens, output_tokens, estimated_cost.
    """
    timestamp: str  # ISO 8601 formatted timestamp string
    model: str
    purpose_tag: str
    input_tokens: int
    output_tokens: int
    estimated_cost: Decimal
    latency_sec: float = 0.0
    success: bool = True
    error_msg: Optional[str] = None

    # Backward compatibility properties
    @property
    def model_name(self) -> str:
        return self.model

    @property
    def purpose(self) -> str:
        return self.purpose_tag

    @property
    def cost_usd(self) -> Decimal:
        return self.estimated_cost

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "purpose_tag": self.purpose_tag,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost": float(self.estimated_cost),
            "latency_sec": round(self.latency_sec, 4),
            "success": self.success,
            "error_msg": self.error_msg,
        }


class LLMTracker:
    """Singleton tracker for intercepting and logging all model calls across the pipeline."""

    _instance: Optional[LLMTracker] = None
    records: List[LLMCallRecord]

    def __new__(cls) -> LLMTracker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.records = []
        return cls._instance

    def reset(self) -> None:
        """Clear all logged records."""
        self.records.clear()

    def record_call(
        self,
        model: Optional[str] = None,
        purpose_tag: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: Optional[Decimal] = None,
        timestamp: Optional[str] = None,
        latency_sec: float = 0.0,
        success: bool = True,
        error_msg: Optional[str] = None,
        # Legacy keyword compatibility
        model_name: Optional[str] = None,
        purpose: Optional[str] = None,
        cost_usd: Optional[Decimal] = None,
    ) -> LLMCallRecord:
        """Record an LLM call with required attributes."""
        chosen_model = model or model_name or "claude-3-5-sonnet-20241022"
        chosen_purpose = purpose_tag or purpose or "general"
        chosen_ts = timestamp or datetime.now(timezone.utc).isoformat()

        if estimated_cost is None:
            if cost_usd is not None:
                chosen_cost = cost_usd
            else:
                chosen_cost = calculate_cost(chosen_model, input_tokens, output_tokens)
        else:
            chosen_cost = estimated_cost

        record = LLMCallRecord(
            timestamp=chosen_ts,
            model=chosen_model,
            purpose_tag=chosen_purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost=chosen_cost,
            latency_sec=latency_sec,
            success=success,
            error_msg=error_msg,
        )
        self.records.append(record)
        return record

    def generate_report_markdown(self, total_requests: int = 250) -> str:
        """
        Generate evaluation/usage_report.md markdown containing:
        1. Overall aggregate usage totals.
        2. Per-request average token count and cost metrics.
        3. Per-model summary breakdown tables.
        4. Purpose breakdown table.
        """
        effective_requests = max(1, total_requests)

        if not self.records:
            return (
                "# LLM Token & Cost Accounting Report\n\n"
                "## 1. Overall Aggregate Usage Totals\n\n"
                "- **Total Model Calls:** 0\n"
                "- **Total Input Tokens:** 0\n"
                "- **Total Output Tokens:** 0\n"
                "- **Total Combined Tokens:** 0\n"
                "- **Total Estimated Cost:** $0.0000 USD\n\n"
                f"## 2. Per-Request Average Metrics (N = {effective_requests} requests)\n\n"
                f"- **Evaluated Requests Count:** {effective_requests}\n"
                "- **Average Calls Per Request:** 0.00\n"
                "- **Average Input Tokens Per Request:** 0.00\n"
                "- **Average Output Tokens Per Request:** 0.00\n"
                "- **Average Total Tokens Per Request:** 0.00\n"
                "- **Average Estimated Cost Per Request:** $0.000000 USD\n\n"
                "## 3. Per-Model Summary Breakdown Table\n\n"
                "| Model | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |\n"
                "| :--- | :---: | :---: | :---: | :---: | :---: |\n"
                "| *(None)* | 0 | 0 | 0 | 0 | $0.0000 |\n"
            )

        total_calls = len(self.records)
        total_in = sum(r.input_tokens for r in self.records)
        total_out = sum(r.output_tokens for r in self.records)
        total_tokens = total_in + total_out
        total_cost = sum(r.estimated_cost for r in self.records)

        avg_calls_per_req = Decimal(total_calls) / Decimal(effective_requests)
        avg_in_per_req = Decimal(total_in) / Decimal(effective_requests)
        avg_out_per_req = Decimal(total_out) / Decimal(effective_requests)
        avg_tokens_per_req = Decimal(total_tokens) / Decimal(effective_requests)
        avg_cost_per_req = total_cost / Decimal(effective_requests)

        # Per model breakdown
        models: Dict[str, Dict[str, Any]] = {}
        for r in self.records:
            if r.model not in models:
                models[r.model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": Decimal(0),
                    "latencies": [],
                }
            models[r.model]["calls"] += 1
            models[r.model]["input_tokens"] += r.input_tokens
            models[r.model]["output_tokens"] += r.output_tokens
            models[r.model]["cost"] += r.estimated_cost
            models[r.model]["latencies"].append(r.latency_sec)

        # Purpose breakdown
        purposes: Dict[str, Dict[str, Any]] = {}
        for r in self.records:
            key = (r.purpose_tag, r.model)
            if key not in purposes:
                purposes[key] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": Decimal(0),
                }
            purposes[key]["calls"] += 1
            purposes[key]["input_tokens"] += r.input_tokens
            purposes[key]["output_tokens"] += r.output_tokens
            purposes[key]["cost"] += r.estimated_cost

        lines = [
            "# LLM Token & Cost Accounting Report",
            "",
            "## 1. Overall Aggregate Usage Totals",
            "",
            f"- **Total Model Calls:** {total_calls:,}",
            f"- **Total Input Tokens:** {total_in:,}",
            f"- **Total Output Tokens:** {total_out:,}",
            f"- **Total Combined Tokens:** {total_tokens:,}",
            f"- **Total Estimated Cost:** ${total_cost:.4f} USD",
            "",
            f"## 2. Per-Request Average Metrics (N = {effective_requests} requests)",
            "",
            f"- **Evaluated Requests Count:** {effective_requests}",
            f"- **Average Model Calls Per Request:** {avg_calls_per_req:.2f} calls/request",
            f"- **Average Input Tokens Per Request:** {avg_in_per_req:.2f} tokens/request",
            f"- **Average Output Tokens Per Request:** {avg_out_per_req:.2f} tokens/request",
            f"- **Average Total Tokens Per Request:** {avg_tokens_per_req:.2f} tokens/request",
            f"- **Average Estimated Cost Per Request:** ${avg_cost_per_req:.6f} USD/request",
            "",
            "## 3. Per-Model Summary Breakdown Table",
            "",
            "| Model | Calls | Input Tokens | Output Tokens | Total Tokens | Avg Latency | Estimated Cost (USD) | Cost Share |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for m_name, data in sorted(models.items()):
            m_total = data["input_tokens"] + data["output_tokens"]
            avg_lat = sum(data["latencies"]) / max(1, len(data["latencies"]))
            share = (data["cost"] / total_cost * Decimal(100)) if total_cost > Decimal(0) else Decimal(0)
            lines.append(
                f"| `{m_name}` | {data['calls']:,} | {data['input_tokens']:,} | "
                f"{data['output_tokens']:,} | {m_total:,} | {avg_lat:.3f}s | ${data['cost']:.4f} | {share:.1f}% |"
            )

        lines.extend([
            "",
            "## 4. Purpose Breakdown Table",
            "",
            "| Purpose Tag | Model | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |",
            "| :--- | :--- | :---: | :---: | :---: | :---: | :---: |",
        ])

        for (p_tag, m_name), data in sorted(purposes.items()):
            p_total = data["input_tokens"] + data["output_tokens"]
            lines.append(
                f"| `{p_tag}` | `{m_name}` | {data['calls']:,} | {data['input_tokens']:,} | "
                f"{data['output_tokens']:,} | {p_total:,} | ${data['cost']:.4f} |"
            )

        lines.append("")
        return "\n".join(lines)

    def write_usage_report(self, filepath: str | Path, total_requests: int = 250) -> None:
        """
        Write markdown usage report to target path and ensure synchronized presence
        in both `code/evaluation/usage_report.md` and `evaluation/usage_report.md`.
        """
        target_path = Path(filepath).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_report_markdown(total_requests=total_requests)

        with open(target_path, mode="w", encoding="utf-8") as f:
            f.write(content)

        # Synchronize with root evaluation directory if appropriate
        try:
            if target_path.parent.name == "evaluation" and target_path.parent.parent.name == "code":
                repo_root = target_path.parent.parent.parent
                root_eval_path = repo_root / "evaluation" / "usage_report.md"
                root_eval_path.parent.mkdir(parents=True, exist_ok=True)
                with open(root_eval_path, mode="w", encoding="utf-8") as f:
                    f.write(content)
            elif target_path.parent.name == "evaluation":
                repo_root = target_path.parent.parent
                code_eval_path = repo_root / "code" / "evaluation" / "usage_report.md"
                code_eval_path.parent.mkdir(parents=True, exist_ok=True)
                with open(code_eval_path, mode="w", encoding="utf-8") as f:
                    f.write(content)
        except Exception:
            pass


def wrap_llm_call(
    fn: Callable[..., Any],
    *args,
    purpose_tag: str = "general",
    model: str = "claude-3-5-sonnet-20241022",
    **kwargs,
) -> Any:
    """
    Executes a callable while intercepting and logging execution duration,
    token metrics, and estimated financial cost.
    """
    tracker = LLMTracker()
    start_t = time.time()
    ts = datetime.now(timezone.utc).isoformat()
    try:
        res = fn(*args, **kwargs)
        latency = time.time() - start_t
        if isinstance(res, tuple) and len(res) == 3:
            actual_result, in_tokens, out_tokens = res
        elif hasattr(res, "usage"):
            actual_result = res
            in_tokens = getattr(res.usage, "input_tokens", 0)
            out_tokens = getattr(res.usage, "output_tokens", 0)
        else:
            actual_result = res
            in_tokens = 0
            out_tokens = 0

        tracker.record_call(
            timestamp=ts,
            model=model,
            purpose_tag=purpose_tag,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            latency_sec=latency,
            success=True,
        )
        return actual_result
    except Exception as e:
        latency = time.time() - start_t
        tracker.record_call(
            timestamp=ts,
            model=model,
            purpose_tag=purpose_tag,
            input_tokens=0,
            output_tokens=0,
            latency_sec=latency,
            success=False,
            error_msg=str(e),
        )
        raise


def track_llm_call(
    purpose_tag: str = "llm_query",
    model: str = "claude-3-5-sonnet-20241022",
    purpose: Optional[str] = None,
    model_name: Optional[str] = None,
):
    """
    Decorator for tracking LLM invocations with automatic metric collection.
    Attributes logged: timestamp, model, purpose_tag, input_tokens, output_tokens, estimated_cost.
    """
    actual_purpose = purpose_tag or purpose or "general"
    actual_model = model or model_name or "claude-3-5-sonnet-20241022"

    def decorator(fn: Callable):
        def wrapper(*args, **kwargs):
            return wrap_llm_call(fn, *args, purpose_tag=actual_purpose, model=actual_model, **kwargs)
        return wrapper
    return decorator
