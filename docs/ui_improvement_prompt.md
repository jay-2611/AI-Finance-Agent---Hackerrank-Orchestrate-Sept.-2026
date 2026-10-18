# Prompt: Improve the Frontend UI for the "Buy or Wait?" Finance Agent

Build/improve the user interface for this financial affordability app. The
backend already returns structured predictions (amount_safe_to_pay,
affordability_status, recommended_payment_method, payment_plan,
earliest_date_for_full_payment, spending_changes_needed,
decision_explanation) for a user's request. Focus purely on the frontend
experience across four areas: upload flow, error handling, privacy
communication, and result readability. This is a finance product — clarity,
trust, and calm design matter more than visual flair.

## 1. Upload flow

- Support two input paths clearly separated: (a) pasting/typing a request in
  plain language ("Can I afford this laptop?"), and (b) attaching supporting
  files — bank statement screenshots, receipts, or CSV exports.
- Show a drag-and-drop zone with explicit accepted formats and size limits
  (e.g. "PNG, JPG, CSV — up to 10MB").
- After a file is added, show a lightweight preview (thumbnail for images,
  filename + row count for CSVs) with a remove/replace option before
  submitting — never submit blind.
- Show a distinct progress state while files are being parsed/extracted
  (e.g. "Reading your screenshot…") separate from the "Calculating your
  recommendation…" state that follows, so the user understands what stage
  is slow and why.
- Disable the submit button until at least a request description is present;
  files should always be optional, never required to get an answer.

## 2. Error handling

- Never show a raw error, stack trace, or backend exception. Translate every
  failure into a plain-language message plus a next step.
- Cover these specific cases with distinct messages:
  - Unreadable or blurry image → "We couldn't read the amount in this image.
    Try a clearer photo or enter the amount manually."
  - Unsupported currency or missing exchange rate → explain which currency
    is affected and what to do.
  - Missing required financial context (e.g. no balance on file) → tell the
    user exactly what's missing, not just that something failed.
  - Model/backend timeout → "This is taking longer than expected" with a
    retry action, not a dead end.
- Inline validation on the request field itself (e.g. flag if requested
  amount is zero or negative) before submission, not just after.
- Every error state should offer one clear recovery action (retry, edit,
  contact support) — never leave the user at a blank or frozen screen.

## 3. Privacy note

- Show a short, plain-language privacy notice near the upload zone and
  before first submission — not buried in a footer link only.
- State clearly and specifically:
  - What data is used (balances, transaction history, uploaded images/files)
  - That uploaded images are used only to extract financial figures and are
    not stored longer than necessary — state your actual retention policy
    here, don't leave a placeholder claim in production
  - That this is a recommendation tool, not financial advice, and not a
    bank or licensed advisor
- Use a dismissible but re-accessible banner or modal, not a wall of legal
  text. Link out to a full privacy policy for anyone who wants more detail.
- If the product later supports real accounts, add a visible indicator of
  whether data is shared with any third party (e.g. the LLM provider) and
  keep that note current — do not let this drift from actual practice.

## 4. Readable results

- Lead with the single most important fact: the affordability_status,
  rendered as a short human label with a clear visual state (e.g. "Yes, you
  can afford this today" / "Not yet — here's when" / "Not recommended right
  now"), not the raw enum value.
- Show `amount_safe_to_pay` and `requested_amount` together for context (e.g.
  a simple progress indicator: "$450 of $600 safe to pay now"), rather than
  amount_safe_to_pay alone.
- Render `payment_plan` as a simple timeline or list of dated payments, not
  a raw pipe-delimited string. Each line: date, amount, running total.
- Show `earliest_date_for_full_payment` only when relevant (i.e. skip it
  entirely when the status is affordable_now, since it's redundant there).
- Turn `spending_changes_needed` into short, specific action items (e.g.
  "Pause your $40/month streaming subscription until Nov 3") instead of the
  raw `stop:event_14` code — resolve event IDs to their human-readable
  names before display.
- Put `decision_explanation` directly under the headline status, in plain
  sentence form, so the user immediately understands why, not just what.
- Avoid financial jargon in all user-facing copy (say "monthly minimum
  balance" not "minimum_balance_to_keep"); reserve raw field names for a
  collapsible "technical details" section for power users only.
- Make the result screen scannable in under 10 seconds: headline status →
  one-line reason → payment plan → any spending changes needed, in that
  order, top to bottom.

## Tone and visual guidance

- Calm, neutral color language: avoid alarming red/green treatments for
  status — use them sparingly and only for the single primary status
  indicator, not throughout the page.
- No dark patterns: never make "wait" or "not affordable" outcomes look
  like failures the user should dismiss or retry against; present them as
  equally valid, calmly-delivered recommendations.
- Keep copy short. Prefer a full sentence over a fragment, but never more
  than two sentences per explanation shown by default.
