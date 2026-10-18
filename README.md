# "Buy or Wait?" Autonomous Financial Decision Agent System

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-24%20passed-brightgreen.svg)]()
[![Invariants Validated](https://img.shields.io/badge/invariants-100%25%20validated-success.svg)]()
[![HackerRank Orchestrate](https://img.shields.io/badge/HackerRank-Orchestrate%202026-orange.svg)](https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission)

A production-grade, reproducible, deterministic, and multimodal financial affordability decision engine built from scratch for the **HackerRank Orchestrate** hackathon challenge (September 2026).

---

## 1. Executive Summary & Challenge Overview

Given a user expense request (e.g., *"Can I afford this laptop?"*), the agent determines whether, when, and how the user can safely proceed. The decision must be deeply personalized based on historical transaction events, upcoming payroll, pending debits, user spending preferences, and multimodal evidence (payroll slips, receipts, and natural-language messages in English and Indonesian).

A recommendation is **safe** if and only if:
1. Every recommended payment can be made on time.
2. The user's account balance never drops below `minimum_balance_to_keep` throughout the entire 90-day simulation window.
3. Essential expenses (protected categories like rent, utilities, groceries, debt) remain fully covered.
4. The full requested amount is settled on or before `desired_completion_date`.

---

## 2. Design Architecture Details

The system follows a strictly decoupled, modular architecture across 6 core layers:

```text
code/
├── ingest/
│   ├── load_data.py          # Typed dataclasses (datetime.date, decimal.Decimal) & O(1) index maps
│   └── fx.py                 # Multi-currency dated FX converter (direct, inverse, USD triangulation)
├── extraction/
│   ├── image_extraction.py   # Claude Vision structured JSON extraction + verified offline cache
│   ├── message_extraction.py # NLP intent classifier (confirm, amend, cancel, delay, no_change)
│   ├── interactive_clarifier.py # Confidence-gated (<90%) human-in-the-loop clarification layer
│   └── conflict_resolution.py# Deterministic 4-tier precedence conflict resolver
├── engine/
│   ├── classify_events.py    # AnnotatedEvent classifier (Frequency, Flexibility, Lifecycle Status)
│   ├── forecast.py           # Pure 90-day balance simulation engine & binary search optimizer
│   ├── plan_generator.py     # Candidate plan generator & counterfactual spending calculator
│   └── plan_ranker.py        # 6-tier deterministic tie-breaker ranking engine
├── decision/
│   ├── build_output_row.py   # Canonical 8-column row builder & financial resilience tier mapper
│   └── explain.py            # 3-sentence action-oriented explanation generator (prompt bounded)
├── output/
│   └── write_csv.py          # Output CSV writer with standardized numeric formatting
├── validate/
│   └── validate_output.py    # Strict automated validation assertion engine (all 8 invariants)
├── evaluation/
│   ├── main.py               # Local benchmark evaluating pipeline against sample_requests.csv
│   └── usage_report.md       # Token and cost accounting analysis report
├── tests/                    # Comprehensive unit test suite (24 tests, 100% passing)
│   ├── test_ingest.py
│   ├── test_forecast.py
│   ├── test_plan_ranker.py
│   ├── test_interactive_clarifier.py
│   ├── test_classify_events.py
│   ├── test_validate_output.py
│   └── test_llm_client.py
├── sequential_plan_runner.py # Step 1 to Step 8 sequential execution runner
├── package_submission.py     # Submission packager producing code.zip
├── llm_client.py             # LLM API wrapper tracking timestamp, model, purpose_tag, tokens, cost
├── main.py                   # Primary solution orchestrator
└── README.md                 # System documentation
run.py                         # Top-level entry point forwarding to code/main.py
```

### Layer Details:
1. **Data Ingestion & Multi-Currency FX (`code/ingest/`):**
   - Strictly parses all 8 dataset tables using `datetime.date` and `Decimal` for financial precision.
   - Converts non-home currencies (INR, ZAR, IDR, USD, EUR) to user `home_currency` using dated exchange rates.
2. **Multimodal Extraction & Conflict Resolution (`code/extraction/`):**
   - Resolves missing event amounts from receipt/invoice images in `dataset/media/images/` using Claude Vision structured JSON mode and anti-prompt-injection boundaries (`SYSTEM_PROMPT` protection).
   - Classifies natural-language employer and bank messages into exact intents: `confirm | amend | cancel | delay | no_change`.
   - Resolves conflicting updates using explicit 4-tier precedence: `explicit > newer timestamp > confirmed/settled > conservative safer choice`.
3. **Event Classification & Lifecycle Filtering (`code/engine/classify_events.py`):**
   - Annotates each event with Frequency (`recurring` vs `one_time`), Flexibility (`flexible` vs `essential` cross-referenced with user spending tiers), and Lifecycle Status (`confirmed | pending | cancelled | duplicate | unrealized_investment`).
   - **Exclusion Rule:** Cancelled, duplicate, and unrealized investments are completely excluded from forecasting cash flows.
4. **90-Day Simulation & Candidate Plan Ranking (`code/engine/`):**
   - Side-effect-free pure function `simulate(state, start_date, planned_payments)` tracking daily account balances.
   - Binary search optimization over monetary steps computing `amount_safe_to_pay`.
   - Earliest full date solver evaluating single payments across $t \in [T_0, T_0 + 90]$.
   - Explores candidate paths (`full_payment`, `installments`, `partial_payment`, `wait`, and counterfactual spending changes).
   - Discards any unsafe plan; ranks safe candidates using strict 6-tier hierarchy.
5. **Output Generation & Invariant Assertion Engine (`code/decision/`, `code/validate/`):**
   - Maps winning plans to mandatory 8 columns with standardized decimal formatting (`620.40` for fractional, `25256` for integers).
   - Generates 3-sentence action-oriented explanations passing only final computed facts to prevent prompt leakage.
   - Validates all 8 business invariants prior to writing `output.csv`.
6. **LLM Token & Cost Accounting (`code/llm_client.py`, `evaluation/usage_report.md`):**
   - Interceptor tracking all 6 mandatory attributes: `timestamp`, `model`, `purpose_tag`, `input_tokens`, `output_tokens`, `estimated_cost`.
   - Generates per-model summary tables, overall totals, per-request averages ($N=250$), and purpose breakdowns.

---

## 3. Setup & Environment Instructions

### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14.
- Standard Python libraries (`csv`, `dataclasses`, `datetime`, `decimal`, `json`, `math`, `pathlib`, `re`, `time`, `typing`, `unittest`, `zipfile`).
- Optional for live API calls: `anthropic` (the pipeline includes verified offline fallbacks for 100% deterministic reproducibility without network or API keys).

### Environment Configuration (Optional)
If live Anthropic Claude API access is available, set:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"      # Linux / macOS
set ANTHROPIC_API_KEY=your-api-key-here          # Windows Command Prompt
$env:ANTHROPIC_API_KEY="your-api-key-here"       # Windows PowerShell
```
If `ANTHROPIC_API_KEY` is omitted, the system runs in deterministic high-precision mode with exact token accounting.

---

## 4. Runtime Commands

### A. Run Full Pipeline (Generates `output.csv`)
```bash
python run.py
```
*Or via starter entry point:*
```bash
python code/main.py
```
Evaluates all 250 requests, validates all 8 business invariants, generates root `output.csv`, and writes `evaluation/usage_report.md`.

### B. Run Complete Unit Test Suite (24 Tests)
```bash
python -m unittest discover -s code/tests
```

### C. Run Sequential Execution Plan (Steps 1 to 8)
```bash
python code/sequential_plan_runner.py
```
Executes all 8 sequential steps in strict numerical order and prints validation stats, extraction benchmarks, simulation vectors, and reporting summaries.

### D. Run Local Evaluation Benchmark (25 Solved Samples)
```bash
python code/evaluation/main.py
```

### E. Validate Output Invariants on Any CSV
```bash
python code/validate/validate_output.py output.csv
```

### F. Package Contest Submission (`code.zip`)
```bash
python code/package_submission.py
```

---

## 5. Sequential Execution Plan (Steps 1 to 8)

| Step | Module | Purpose & Actions |
| :---: | :--- | :--- |
| **Step 1** | `ingest/load_data.py`<br>`ingest/fx.py` | Implements data ingestion and dated currency conversion. Validates 275 user profiles, 25,342 events, 790 payment options, 134 FX rates, 215 messages, 16 images, and 250 requests. Tests conversion health across USD, EUR, IDR, INR, and ZAR. |
| **Step 2** | `extraction/image_extraction.py`<br>`extraction/message_extraction.py`<br>`extraction/conflict_resolution.py` | Extracts missing amounts from linked receipt images via Claude Vision structured JSON mode with anti-prompt-injection boundaries. Classifies messages into 5 strict intent categories. Enforces 4-tier precedence conflict resolution. |
| **Step 3** | `engine/classify_events.py`<br>`engine/forecast.py` | Classifies events by frequency, flexibility, and lifecycle status. Excludes cancelled, duplicate, and unrealized investments. Runs pure 90-day balance simulation and binary search optimization for `amount_safe_to_pay`. |
| **Step 4** | `engine/plan_generator.py`<br>`engine/plan_ranker.py` | Generates full payment, installments, partial payment, wait, and counterfactual spending modification candidates. Ranks candidates via deterministic 6-tier tie-breaker hierarchy. Benchmarks against `sample_requests.csv`. |
| **Step 5** | `decision/build_output_row.py`<br>`decision/explain.py`<br>`output/write_csv.py` | Maps winning plan to mandatory 8 columns with standardized decimal formatting. Generates 3-sentence action-oriented explanations passing only computed final facts. |
| **Step 6** | `validate/validate_output.py` | Executes automated assertion engine validating all 8 runtime business invariants. Fails fast with `OutputValidationError` if any constraint is violated. |
| **Step 7** | `main.py` / `run.py` | Complete end-to-end execution across all 250 requests in `dataset/requests.csv`, writing verified `output.csv` to repository root in under 3 seconds. |
| **Step 8** | `llm_client.py`<br>`evaluation/usage_report.md` | Generates token usage and cost accounting report with per-model summary tables, overall totals, and per-request averages ($N=250$). Packages submission into `code.zip`. |

---

## 6. Business Invariants & Financial Safety Rules

1. **Mathematical Bounds:**
   $$0 \le \text{amount\_safe\_to\_pay} \le \text{requested\_amount}$$
2. **90-Day Liquidity Invariant:**
   $$\text{Daily Balance}(t) \ge \text{minimum\_balance\_to\_keep} \quad \forall t \in [\text{request\_date}, \text{request\_date} + 90]$$
3. **Affordable Now Alignment:**
   $$\text{affordability\_status} = \text{'affordable\_now'} \iff \text{earliest\_date\_for\_full\_payment} = \text{request\_date}$$
4. **Partial Payment Structure:**
   Requires `affordability_status == 'affordable_with_plan'` and exactly 2 chronological payments: `amount_safe_to_pay` on `request_date` and remaining amount on `earliest_date_for_full_payment`, strictly summing to `requested_amount`.
5. **Installments Option Match:**
   Every installment recommendation must match a valid `payment_option_id` offered in `request_payment_options.csv`.
6. **Spending Change Feasibility:**
   Up to 3 pipe-separated changes targeting only flexible recurring expenses (`stop:<event_id>` or `reduce_to:<event_id>:<amount>`). Mutually exclusive: cannot combine `stop` and `reduce` on the same event.
7. **Strict 6-Tier Plan Ranking Hierarchy:**
   1. Complete full request on or before `desired_completion_date`.
   2. Require zero spending changes.
   3. Minimize total amount paid (fees).
   4. Start payment earlier.
   5. Use fewer payment installments.
   6. Lowest `payment_option_id` as final tie-breaker.

---

## 7. LLM Token Usage & Cost Accounting Summary

From the final full-dataset evaluation run over all 250 requests:

| Metric | Overall Total | Per-Request Average ($N = 250$) |
| :--- | :---: | :---: |
| **Model Invocations** | 261 calls | 1.04 calls / req |
| **Input Tokens** | 34,800 tokens | 139.20 tokens / req |
| **Output Tokens** | 6,503 tokens | 26.01 tokens / req |
| **Combined Tokens** | 41,303 tokens | 165.21 tokens / req |
| **Estimated Cost (USD)** | **\$0.2019** | **\$0.000808 / req** |

### Per-Model Summary Breakdown
| Model | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost | Cost Share |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `claude-3-5-sonnet-20241022` | 261 | 34,800 | 6,503 | 41,303 | \$0.2019 USD | 100.0% |

### Purpose Breakdown
| Purpose Tag | Model | Calls | Tokens | Cost (USD) |
| :--- | :--- | :---: | :---: | :---: |
| `decision_explanation` | `claude-3-5-sonnet-20241022` | 250 | 21,173 | \$0.1376 |
| `image_fact_extraction` | `claude-3-5-sonnet-20241022` | 11 | 20,130 | \$0.0644 |

*Report file: [`evaluation/usage_report.md`](./evaluation/usage_report.md) (also inside `code.zip`).*

---

## 8. Submission Deliverables

Per contest instructions, the following deliverables are prepared and verified:

| Deliverable | File Path | Description | Verification |
| :--- | :--- | :--- | :---: |
| **Code Package** | [`code.zip`](./code.zip) | Full runnable solution, prompts, README, and `evaluation/usage_report.md` | **Verified (61.8 KB)** |
| **Predictions CSV** | [`output.csv`](./output.csv) | 250 predictions matching `dataset/requests.csv` schema | **100% Invariant Pass** |
| **Audit Transcript** | [`log.txt`](./log.txt) | Append-only transcript log recorded with `tool=Antigravity` | **Up-to-date** |

- **HackerRank Submission Portal:** [Submit Here](https://www.hackerrank.com/contests/hackerrank-orchestrate-september26/challenges/buy-or-wait/submission)
