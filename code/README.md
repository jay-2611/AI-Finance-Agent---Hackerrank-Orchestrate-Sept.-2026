# "Buy or Wait?" Autonomous Financial Decision Agent System

Autonomous financial affordability decision engine built for the **HackerRank Orchestrate** hackathon challenge (September 2026).

---

## 1. System Overview

Given a user expense request, the agent decides whether a user can safely afford it by forecasting daily balances over a 90-day horizon, ensuring:
1. Every payment is covered on its scheduled date.
2. Protected essential expenses (rent, utilities, groceries, debt) are strictly covered.
3. The user's balance never falls below `minimum_balance_to_keep` at any point in the 90-day window.

---

## 2. Directory Structure

```text
code/
├── ingest/
│   ├── load_data.py          # Strict date (datetime.date) & monetary (decimal.Decimal) CSV loader
│   └── fx.py                 # Multi-currency dated converter with inverse & triangulation
├── extraction/
│   ├── image_extraction.py   # Multimodal receipt/invoice amount extraction with Claude Vision & cache
│   ├── message_extraction.py # Intent parsing for salary, rent, and invoice amendments
│   ├── interactive_clarifier.py # Confidence-gated (<90%) human-in-the-loop clarifier
│   └── conflict_resolution.py# Priority rule engine for contradictory financial records
├── engine/
│   ├── classify_events.py    # Clean state reconstructor & AnnotatedEvent structured classifier
│   ├── forecast.py           # Pure 90-day daily balance cash flow simulation engine & optimizer
│   ├── plan_generator.py     # Candidate plan generator & counterfactual what-if calculator
│   └── plan_ranker.py        # 6-tier deterministic tie-breaker ranker
├── decision/
│   ├── build_output_row.py   # Output row builder & financial resilience tier mapper
│   └── explain.py            # 3-sentence action-oriented explanation persona
├── output/
│   └── write_csv.py          # Output CSV writer with standardized numeric formatting
├── validate/
│   └── validate_output.py    # Business invariant assertion engine
├── evaluation/
│   ├── main.py               # Local benchmark against 25 sample requests
│   └── usage_report.md       # Token and cost analysis report
├── tests/                    # Complete unit test suite (24 tests, 100% passing)
│   ├── test_ingest.py        # Ingestion & FX conversion unit tests
│   ├── test_forecast.py      # Balance simulation unit tests
│   ├── test_plan_ranker.py   # Plan ranking unit tests
│   ├── test_interactive_clarifier.py # Clarification protocol tests
│   ├── test_classify_events.py       # Event annotation & exclusion tests
│   ├── test_validate_output.py       # Schema validation tests
│   └── test_llm_client.py            # Token tracking & cost report tests
├── sequential_plan_runner.py # Step 1 to Step 8 sequential execution runner
├── package_submission.py     # Clean ZIP packager creating root code.zip
├── llm_client.py             # LLM API wrapper with token & cost tracking decorators
├── main.py                   # Primary execution orchestrator
└── README.md                 # System documentation
```

---

## 3. Quick Start & Execution

### Running the End-to-End Pipeline
To run the full pipeline and generate predictions in `output.csv` at the repository root:
```bash
python run.py
```
Or directly via the starter entry point:
```bash
python code/main.py
```

### Running the Complete Test Suite (24 Tests)
```bash
python -m unittest discover -s code/tests
```

### Running the Sequential Execution Plan (Steps 1 to 8)
```bash
python code/sequential_plan_runner.py
```

### Running Local Evaluation Benchmark (25 Solved Samples)
```bash
python code/evaluation/main.py
```

### Validating Output Invariants
```bash
python code/validate/validate_output.py output.csv
```

### Packaging Contest Submission
```bash
python code/package_submission.py
```

---

## 4. Key Financial Rules Enforced

- **90-Day Safety Invariant:** $\text{Balance}(t) \ge \text{minimum\_balance\_to\_keep} \quad \forall t \in [T_0, T_0 + 90]$.
- **Pending & Unrealized Constraints:** Pending debits reserved immediately; pending credits and unrealized investments excluded until settled.
- **Strict Bounds:** $0 \le \text{amount\_safe\_to\_pay} \le \text{requested\_amount}$.
- **Method Consistency:** Installments must match a supplied `payment_option_id`. Partial payment must be exactly 2 payments.
- **Deterministic 6-Tier Ranking:**
  1. Complete by deadline
  2. 0 spending changes
  3. Minimum total amount paid (fees)
  4. Earliest start date
  5. Fewer payment installments
  6. Lowest `payment_option_id`
