# LLM Token & Cost Accounting Report

## 1. Overall Aggregate Usage Totals

- **Total Model Calls:** 261
- **Total Input Tokens:** 34,800
- **Total Output Tokens:** 12,794
- **Total Combined Tokens:** 47,594
- **Total Estimated Cost:** $0.2963 USD

## 2. Per-Request Average Metrics (N = 250 requests)

- **Evaluated Requests Count:** 250
- **Average Model Calls Per Request:** 1.04 calls/request
- **Average Input Tokens Per Request:** 139.20 tokens/request
- **Average Output Tokens Per Request:** 51.18 tokens/request
- **Average Total Tokens Per Request:** 190.38 tokens/request
- **Average Estimated Cost Per Request:** $0.001185 USD/request

## 3. Per-Model Summary Breakdown Table

| Model | Calls | Input Tokens | Output Tokens | Total Tokens | Avg Latency | Estimated Cost (USD) | Cost Share |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `claude-3-5-sonnet-20241022` | 261 | 34,800 | 12,794 | 47,594 | 0.000s | $0.2963 | 100.0% |

## 4. Purpose Breakdown Table

| Purpose Tag | Model | Calls | Input Tokens | Output Tokens | Total Tokens | Estimated Cost (USD) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `decision_explanation` | `claude-3-5-sonnet-20241022` | 250 | 15,000 | 12,464 | 27,464 | $0.2320 |
| `image_fact_extraction` | `claude-3-5-sonnet-20241022` | 11 | 19,800 | 330 | 20,130 | $0.0644 |
