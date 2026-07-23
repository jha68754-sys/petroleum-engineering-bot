# Petroleum Engineering Telegram Bot — Full Code Audit Report

**Scope reviewed:** every file in the repository (main.py, config.py, constants.py, logging_config.py,
handlers/*, services/*, models/*, prompts/*, templates/*, Procfile, railway.toml, requirements.txt,
runtime.txt, test_409_fix.py, investigation_notes.txt).

**Method:** static line-by-line review + cross-check of every deterministic formula against published
petroleum-engineering literature + reasoning about the Telegram long-polling/Railway deploy lifecycle.

---

## SECTION B — Telegram 409 Root Cause (read this first)

The code itself implements a **single, correctly-serialized polling loop** — there is only one
`get_updates()` call site (`services/telegram_service.py:149`), it is invoked from exactly one
`while running:` loop in `main.py:552`, there is no threading, no asyncio, no `Application.run_polling()`,
and `if __name__ == "__main__"` guards entry (`main.py:602`). `investigation_notes.txt` reached the same
conclusion but was written against an older revision (its cited line numbers no longer match; the
token-redaction gap it flagged is already fixed in the current `logging_config.py`). **The 409 is not
caused by duplicate code paths inside this repository.** It is caused by two interacting
deployment/timing defects, both fully evidenced in the repo:

### B1 — CRITICAL: Graceful-shutdown window is shorter than the long-poll timeout, so old and new containers overlap
- **Files:** `main.py` (`run()`, lines 469, 491-496, 534-544, 552-577) and `config.py` (lines 38, and the
  fact `AI_REQUEST_TIMEOUT`/`POLLING_TIMEOUT` govern blocking HTTP calls).
- **Mechanism:**
  1. `get_updates()` issues `session.get(..., params={"timeout": POLLING_TIMEOUT=30}, timeout=timeout+10=40)`
     (`telegram_service.py:164-169`). This is a **blocking** call that can legitimately sit open for up to 40s.
  2. On Railway redeploy/restart, SIGTERM is sent to the **old** container. `shutdown_handler` (`main.py:534`)
     only sets `running = False` — it cannot interrupt the in-flight blocking `requests` call. Per PEP 475,
     Python transparently retries interrupted syscalls, so the socket read is **not** aborted by the signal.
     The old process will keep polling until its *current* `get_updates` call naturally returns (up to ~40s),
     and only then reach the `finally:` block that calls `tg.delete_webhook()` (`main.py:584`) and exits.
  3. Meanwhile the **new** container starts immediately and only waits `STARTUP_DELAY_SECONDS` (default **8s**,
     `main.py:469`) before it calls `delete_webhook()` and starts its own `get_updates()` loop.
  4. Because 8s (new container's delay) << ~40s (old container's worst-case in-flight poll duration), there is
     a real window — every single deploy — where **two processes hold simultaneous long-poll connections to
     `getUpdates` with the same bot token**. Telegram's API enforces a single `getUpdates` consumer per token
     and returns exactly the error in the ticket: `409 Conflict: terminated by other getUpdates request`.
  5. This also means the old container's `delete_webhook()`-on-shutdown may not even run before Railway's own
     SIGKILL grace period expires, leaving no guarantee the "clean handoff" ever completes.
- **Evidence this is real, not speculative:** `STARTUP_DELAY_SECONDS` (8s) is hard-coded shorter than
  `POLLING_TIMEOUT + 10` (40s) with no relationship enforced between the two constants anywhere in the code.
- **Exact fix:**
  - Increase `STARTUP_DELAY` to safely exceed the worst-case shutdown time of the *previous* instance:
    `STARTUP_DELAY_SECONDS >= POLLING_TIMEOUT + 15` (i.e. ≥ 45s), set via Railway env var `STARTUP_DELAY=45`,
    **or** better:
  - Make the poll interruptible: run `get_updates()` in a background thread/short-timeout loop so
    `shutdown_handler` can set an event that is checked every ~2-3s instead of blocking 40s, then call
    `delete_webhook()` immediately on SIGTERM instead of waiting for the in-flight call.
  - Simplest robust fix: reduce `POLLING_TIMEOUT` to something like 10s (still efficient long-polling) so the
    maximum overlap window shrinks, combined with `STARTUP_DELAY >= 25s`.

### B2 — CRITICAL: `railway.toml` defines an HTTP healthcheck for a service that has no HTTP server
- **File:** `railway.toml`, lines 6-7: `healthcheckPath = "/"`, `healthcheckTimeout = 100`.
- **Evidence:** `grep` across the entire repo for Flask/FastAPI/`http.server`/`socketserver`/`app.run`/`PORT`
  found **nothing** — this is a pure long-polling worker with no bound port and no web server of any kind.
- **Mechanism:** Per Railway's own documented behavior, `deploy.healthcheckPath` only succeeds if the
  application actually serves that route; otherwise "Railway's check never passes and the deploy is held
  back" (Railway keeps the **previous** deployment's container alive and serving/running while it retries the
  new one, since the new one never reports healthy). With `restartPolicyMaxRetries = 5` (line 9), Railway will
  repeatedly start **new container instances** of `main.py`, each of which deletes the webhook and begins
  polling `getUpdates`, **while the still-running old deployment is also polling** (Railway does not tear down
  the old deployment until the new one is confirmed healthy, which it never will be). This alone is sufficient
  to cause persistent/repeating 409s on every deploy, independent of B1.
- **Exact fix:** For a worker with no public endpoint, **remove** `healthcheckPath` and `healthcheckTimeout`
  from `railway.toml` entirely:
  ```toml
  [deploy]
  startCommand = "python3 main.py"
  restartPolicyType = "ON_FAILURE"
  restartPolicyMaxRetries = 5
  ```
  (Also consider `restartPolicyType = "ON_FAILURE"` instead of `"ALWAYS"` — `ALWAYS` will restart the process
  even after a clean intentional exit, which is not appropriate for a singleton poller.)

### B3 — Contributing/verify-externally: no single-instance lock
- Even with B1/B2 fixed, nothing in the repo prevents a human from running a second `python3 main.py` locally
  (or a duplicate Railway service/environment configured with the same `TELEGRAM_BOT_TOKEN`) while the Railway
  deployment is live. The code has no distributed lock (e.g., a Postgres/Redis advisory lock, or Telegram's own
  webhook-vs-polling exclusivity check beyond `getWebhookInfo`).
- **Fix (defense in depth):** on startup, call `getWebhookInfo`/rely on the existing `get_updates` 409 handler,
  but additionally treat **repeated** 409s (e.g., 3 in a row) as a signal to back off for a longer cool-down
  (30-60s) before retrying, rather than the current fixed 5s (`main.py:577`), to reduce collision probability
  during any transient overlap and make the failure self-healing rather than a tight error loop.

**Conclusion of Section B:** the root cause is **external to the Python application logic** (no duplicate
`getUpdates` call sites exist), but it **is** inside this repository, in the **deployment configuration and
shutdown-timing assumptions** (`railway.toml` healthcheck + `main.py`/`config.py` timing constants). If both
B1 and B2 are fixed and the 409s persist, the remaining external cause to check is a second Railway
service/environment or a developer's local instance sharing the same bot token (B3).

---

## SECTION A — Critical Bugs (non-Telegram)

### A1 — CRITICAL: `/analyze` and `/graph` commands are non-functional (silently do nothing)
- **File:** `handlers/text_handlers.py`, `handle_analyze` (lines 394-402) and `handle_graph` (lines 405-413).
- **File:** `main.py`, dispatch block lines 277-294.
- **Explanation:** `handle_analyze`/`handle_graph` return `(None, None, None)` with a comment "Signal that AI
  analysis is needed" — but `main.py`'s dispatch code never checks for this signal:
  ```python
  handler = registry.dispatch(text)
  if handler:
      result_text, png_bytes, doc_filename = handler(message, tg)
      if result_text:      # None -> falsy -> skipped
          ...
      if png_bytes:        # None -> falsy -> skipped
          ...
      if doc_filename and png_bytes is None:  # None -> skipped
          ...
      return               # <-- returns unconditionally, no fallback to AI
  ```
  There is no code path anywhere that calls `ai.ask_text`/`ai.ask_vision` in response to `/analyze` or
  `/graph` when context exists. Meanwhile `file_handlers.py` explicitly tells the user "Ready for `/analyze`"
  (line 110) and "Use `/graph` to analyze" (line 174) — **the documented, advertised workflow is broken**: a
  user who uploads a document/photo and follows the bot's own instructions gets a silent no-op (bot sends
  nothing at all).
- **Exact fix:** in `main.py`, after the registry dispatch, special-case these two commands (or use the
  `(None, None, None)` sentinel that already exists) to fall through to `_handle_free_text`:
  ```python
  handler = registry.dispatch(text)
  if handler:
      result_text, png_bytes, doc_filename = handler(message, tg)
      if result_text is None and png_bytes is None and doc_filename is None:
          # Sentinel for "delegate to AI" (used by /analyze, /graph)
          _handle_free_text(message, text, tg, ai)
          return
      ...
  ```

### A2 — HIGH: `HELP_MESSAGE` is defined twice in `constants.py` (duplicate knowledge, dead code)
- **File:** `constants.py`, lines 1084-1125 (first definition) and 1156-1195 (second definition).
- **Explanation:** Python silently uses the second assignment; the first ~40-line block is dead code. The two
  versions have drifted slightly (the first says "v4.1" and omits "BLOCK 5" wording used elsewhere in the
  codebase; the second doesn't mention the version). This is exactly the "duplicated knowledge" failure mode
  called out in the audit objectives — two sources of truth for the same user-facing text, one silently
  ignored, both able to drift further apart in future edits.
- **Exact fix:** delete the first block (lines 1084-1125) and keep only one canonical `HELP_MESSAGE`.

### A3 — MEDIUM: `IMAGE_CONTEXT`/`FILE_CONTEXT` grow without bound and leak temp files to disk
- **File:** `main.py`, lines 78-80 (module-level dicts, never pruned per-chat except via `/reset`);
  `handlers/file_handlers.py` `handle_photo_upload` (line 165-170) writes a temp file per photo upload and
  stores its path forever in `IMAGE_CONTEXT` unless the user runs `/reset`.
- **Explanation:** Every distinct `chat_id` that ever uploads a file/photo adds a permanent entry to these
  process-global dicts; entries are only removed by an explicit `/reset` command, never by TTL/LRU eviction.
  Over the life of a long-running bot serving many users this is an unbounded memory leak (`FILE_CONTEXT`
  strings can be up to `MAX_CONTEXT_CHARS` = 20,000 chars each) and an unbounded **disk** leak (each photo
  upload writes a file under the OS temp dir via `tempfile.mkstemp`, cleaned up only in the `finally:` block
  of `run()` at process shutdown — i.e., only when the whole bot restarts, not per-chat).
- **Exact fix:** add a simple LRU/TTL eviction (e.g., cap `FILE_CONTEXT`/`IMAGE_CONTEXT` at N most-recently-used
  chats, and delete the on-disk file the moment a chat's image entry is evicted or replaced by a new upload,
  not only on `/reset` or process exit).

### A4 — LOW: `handle_photo_upload` has no upload-size limit (unlike `handle_document_upload`)
- **File:** `handlers/file_handlers.py`, lines 133-176 — `MAX_UPLOAD_SIZE` is imported and checked in
  `handle_document_upload` (line 57-62) but never checked in `handle_photo_upload`.
- **Fix:** add the same `if file_size > MAX_UPLOAD_SIZE: return ...` guard using `best_photo.get("file_size", 0)`.

---

## SECTION C — Railway/Deployment Problems

| # | Severity | File:Line | Issue | Fix |
|---|----------|-----------|-------|-----|
| C1 | Critical | `railway.toml:6-7` | `healthcheckPath="/"` with no HTTP server anywhere in the app (see B2) | Remove `healthcheckPath`/`healthcheckTimeout` |
| C2 | High | `main.py:469` | `STARTUP_DELAY` default (8s) shorter than worst-case shutdown time of previous instance (~40s, see B1) | Raise to ≥45s or make polling interruptible |
| C3 | Medium | `railway.toml:8` | `restartPolicyType = "ALWAYS"` restarts the process even on a clean/intentional exit (e.g., missing config causes `run()` to `return` cleanly at `main.py:505`, which will then be immediately restarted in a loop rather than surfacing the config error) | Use `"ON_FAILURE"` |
| C4 | Low | `Procfile` + `railway.toml` both define the start command | Redundant, not harmful (Railway prefers `railway.toml`), but a future edit to one and not the other risks divergence | Keep one source of truth; delete `Procfile` or keep it in sync as a documented fallback |
| C5 | Low | `config.py:115,122` | `TEMP_DIR` and `OFFSET_STATE_FILE` default to ephemeral/relative paths with **no Railway volume** configured. On every redeploy (new container = new filesystem) the persisted `offset_state.json` is lost unless a Railway volume is mounted at that path, contradicting the docstring "Persistent offset (survives Railway restarts)" | Mount a Railway volume at the directory containing `OFFSET_STATE_FILE`, or accept that offset persistence only survives in-place restarts, not redeploys, and document this |

---

## SECTION D — AI Architecture Problems

### D1 — HIGH: AI response cache key truncation can return answers for the wrong question
- **File:** `services/ai_service.py`, line 263: `cache_key = json.dumps(messages, sort_keys=True)[:2000]`.
- **Explanation:** Every request's `messages` list starts with the system prompt (`self.system_prompt`) and
  the large fixed `engineering_context` block (built once in `_build_engineering_context`, easily several
  thousand characters — it serializes the entire `KNOWLEDGE_BASE`, `PVT_PLOT_RULES`, `EXACT_FORMULAS`, and
  `CORRELATIONS`). Because `json.dumps(messages, sort_keys=True)` serializes messages **in list order**
  (system prompt, then engineering context, then history, then the actual user question), and only the
  **first 2000 characters** of that JSON string are used as the cache key, the user's actual question can be
  truncated away entirely if the fixed preamble already exceeds 2000 characters. Two different user questions
  that share the same conversation history can collide on the same cache key and one user could receive a
  cached answer that was actually generated for a **different, unrelated question**. This is a direct
  hallucination/incorrect-answer risk introduced by the caching layer itself.
- **Exact fix:** hash the *user-relevant* tail of the prompt (last user message + chat history), not a
  truncated prefix of the whole serialized message list, e.g.:
  ```python
  cache_key = hashlib.sha256(
      json.dumps({"h": chat_history[-10:] if chat_history else [], "u": user_message, "f": file_context},
                 sort_keys=True).encode()
  ).hexdigest()
  ```

### D2 — MEDIUM: Full knowledge base re-serialized and re-sent on every single AI call
- **File:** `services/ai_service.py`, `_build_engineering_context` (called once in `__init__`, but the full
  resulting string is appended as a message on **every** `ask_text`/`ask_vision` call, lines 246, 365).
- **Explanation:** This is a performance/cost issue (Section G) but also an AI-quality issue: injecting the
  knowledge base as a message with `"role": "assistant"` (lines 246, 365) — i.e., pretending the model already
  said this in a prior turn — is a known "fake prior turn" grounding trick; it generally works but is more
  fragile than putting the same content in the `system` role, since some providers/models weight system vs.
  assistant turns differently and a sufficiently long fake assistant turn can be partially truncated by
  server-side context windows before the real system prompt's instructions are enforced. Recommend
  consolidating system_prompt + engineering_context into a single `system` message.

### D3 — MEDIUM: `TEXT_FIXES` silently strips all `[` and `]` characters from every cleaned response
- **File:** `constants.py`, line 1133: `"[": "", "]": ""`; applied in `main.py:204-208` (`clean_text`), used
  on every AI free-text response and every command output except `/start`.
- **Explanation:** This silently destroys any bracketed unit notation, citation marker, or list/array
  notation the AI (or a formula's `units` dict, if ever surfaced through free text) produces — e.g. a response
  containing "GOR [scf/STB]" becomes "GOR scf/STB" (readable but silently lossy), and any AI-generated
  markdown-style reference like "[1]" or table-like bracket notation vanishes without a trace. This looks like
  a workaround for a specific bad AI output pattern that was never scoped down.
- **Fix:** remove the blanket `[`/`]` stripping, or scope it to a specific known-bad pattern via regex rather
  than a global character strip.

### D4 — LOW: Vision retry budget (`AI_MAX_VISION_RETRIES = 2`, `config.py:73`) is half of text retries (`AI_MAX_RETRIES = 3`, `config.py:72`) with no stated rationale; vision calls carry a full base64-encoded image in the payload and are more likely to hit transient network/size issues, so the lower retry budget increases user-visible failure rate for the exact feature (`/graph`) that (per A1) is already broken end-to-end.

---

## SECTION E — Petroleum Engineering Problems (verified against literature)

### E1 — CRITICAL: `bo_standing` correlation has an erroneous extra square root — wrong Bo values
- **File:** `constants.py`, lines 857-872, specifically the closing `) ** 0.5` on line 869.
- **Correct Standing (1947) correlation (verified against multiple independent references — Boyun Guo,
  *Petroleum Production Engineering*; Well Productivity Handbook; ScienceDirect topic pages):**
  `Bo = 0.9759 + 0.00012 * (Rs*sqrt(γg/γo) + 1.25*T)^1.2` — **no outer square root over the whole expression.**
- **Code as written:**
  ```python
  "func": lambda rs, gas_sg, tres, api: (
      0.9759 + 0.000120 * (
          rs * (gas_sg / (141.5 / (api + 131.5))) ** 0.5
          + 1.25 * tres
      ) ** 1.2
  ) ** 0.5,   # <-- BUG: entire (0.9759 + 0.00012*F^1.2) is wrongly raised to the power 0.5
  ```
  The inner `sqrt(γg/γo)` (`** 0.5` on line 866) is correct. The **outer** `** 0.5` on line 869 is not part of
  the published correlation and corrupts every result. For a realistic Bo of ~1.30 rb/STB, this bug returns
  `sqrt(1.30) ≈ 1.140` — an ~12% low-bias error; for Bo near 2.0 (volatile oils) the error grows to ~29% low.
  The `formula_str` docstring on line 863 also encodes a (different, but still wrong) misplaced exponent,
  confirming this is an authoring error, not a deliberate simplification.
- **Exact fix:**
  ```python
  "func": lambda rs, gas_sg, tres, api: (
      0.9759 + 0.000120 * (
          rs * (gas_sg / (141.5 / (api + 131.5))) ** 0.5
          + 1.25 * tres
      ) ** 1.2
  ),
  ```
  and correct `formula_str` to `"Bob = 0.9759 + 0.000120 * (Rs*sqrt(gamma_g/gamma_o) + 1.25*T)^1.2"`.

### E2 — CRITICAL: `pb_vasquez_beggs` / `rs_vasquez_beggs` do not implement the Vasquez-Beggs correlation at all, and silently ignore the `p_sep` input they require
- **File:** `constants.py`, lines 830-855.
- **Correct Vasquez-Beggs (1980)** (verified against JPT 968-970, June 1980 and multiple secondary sources)
  requires: (a) **two sets of empirical coefficients C1/C2/C3** branched on API ≤ 30 vs. API > 30 (e.g.
  C1=0.0362, C2=1.0937, C3=25.724 for API≤30; C1=0.0178, C2=1.187, C3=23.931 for API>30 — values vary slightly
  by source but the branching is universal); (b) an **exponential** term in API/(T+460), not a power-of-ten
  term in the Standing style; and (c) the gas gravity must first be **normalized to a reference separator
  pressure of 100 psig** using a correction that explicitly consumes separator pressure and temperature:
  `γgs = γg * [1 + 5.912e-5 * API * Tsep * log10(Psep/114.7)]`.
- **Code as written:**
  ```python
  "rs_vasquez_beggs": {
      "inputs": ["p", "gas_sg", "tres", "api", "p_sep"],
      ...
      "func": lambda p, gas_sg, tres, api, p_sep: gas_sg * (
          p ** 1.0937 * 10 ** (0.0125 * api - 0.00091 * tres)
      ),
      ...
  },
  "pb_vasquez_beggs": {
      "inputs": ["rs", "gas_sg", "tres", "api", "p_sep"],
      ...
      "func": lambda rs, gas_sg, tres, api, p_sep: (
          (111.726 * rs / gas_sg) / (10 ** (0.00091 * tres - 0.0125 * api))
      ) ** 0.83,
      ...
  },
  ```
  Both lambdas **declare `p_sep` as a parameter but never use it in the body** — it is accepted from the user
  (the `/estimate` usage text and `applicability` dict both advertise it as required input, see
  `services/pvt_engine.py` `run_correlation`) and then silently discarded. There is no API-based coefficient
  branching, no exponential term, and no separator-pressure gas-gravity correction anywhere. What's implemented
  is structurally a re-skinned Standing equation with different constants — it is **not** Vasquez-Beggs, and
  it will produce numerically wrong estimates while being labeled with a specific, citable correlation name
  (a hallucination-adjacent risk: the bot will confidently cite "Vasquez-Beggs (1980)" for numbers that
  correlation never produces).
- **Exact fix:** implement the real two-branch correlation, e.g.:
  ```python
  def _vb_coeffs(api):
      return (0.0362, 1.0937, 25.724) if api <= 30 else (0.0178, 1.1870, 23.931)

  def _gas_gravity_at_ref_sep(gas_sg, api, p_sep, t_sep=100.0):
      return gas_sg * (1 + 5.912e-5 * api * t_sep * math.log10(max(p_sep, 1e-6) / 114.7))

  def rs_vasquez_beggs(p, gas_sg, tres, api, p_sep):
      c1, c2, c3 = _vb_coeffs(api)
      ggs = _gas_gravity_at_ref_sep(gas_sg, api, p_sep)
      return c1 * ggs * p ** c2 * math.exp(c3 * api / (tres + 460))
  ```
  and derive `pb_vasquez_beggs` by inverting that same equation for `P` at `Rs = Rsb`. At minimum, until this
  is properly implemented, **remove `pb_vasquez_beggs`/`rs_vasquez_beggs` from the bot** rather than serve
  silently-wrong numbers under a real correlation's name.

### E3 — MEDIUM: `FLUID_CLASSIFICATION_TABLE` "Dry Gas" bucket is unreachable / physically backwards
- **File:** `constants.py`, lines 280-286.
- **Explanation:** The table classifies "Dry Gas" only when `gor_min=0 and gor_max=0` **and**
  `api_min=0 and api_max=0` — i.e., only for the exact input `GOR=0, API=0`. Physically, a dry gas reservoir
  has essentially **no liquid production at all**, which in practice means GOR is undefined/very high (no
  stock-tank oil to divide by), not zero — and API gravity is not even a meaningful property of a fluid that
  never condenses to liquid at surface. As coded, any real dry-gas dataset (e.g., GOR reported as a very large
  number, or API omitted/entered as 0 by convention) will either fall through to "Wet Gas" (if GOR>100,000) or
  to the "Unknown/no match" branch in `classify_fluid` (`services/pvt_engine.py:62-70`) — the Dry Gas label is
  effectively dead code for realistic inputs.
- **Fix:** classify Dry Gas by a *separate* signal (e.g., an explicit "no liquid produced" flag or GOR above
  some very high threshold combined with near-zero condensate yield) rather than by API/GOR bounds that can
  never be satisfied by a real sample.

### E4 — LOW: Boundary ambiguity between adjacent fluid classes
- **File:** `constants.py`, lines 251-287 (`Black Oil` api_max=40 / `Volatile Oil` api_min=40, and
  `Black Oil` gor_max=2000 / `Volatile Oil` gor_min=2000).
- **Explanation:** `classify_fluid` (`services/pvt_engine.py:46-47`) returns the **first** matching row, so a
  sample at exactly GOR=2000 or API=40 is always classified as "Black Oil," silently masking the boundary
  case rather than flagging it as borderline. Not incorrect per se, but worth an explicit "borderline" note
  in the output when a value sits exactly on a class boundary, since real fluids at these exact values are
  genuinely ambiguous.

### E5 — LOW: `_validate_density_trend` is a stub that always returns `True`
- **File:** `services/pvt_engine.py`, lines 360-369: `return True  # Simplified -- full check similar to Bo mirror`.
- **Explanation:** `/check density ...` will report "All trends PASS physical validation" regardless of the
  actual data — a false-confidence risk for a tool whose entire selling point is deterministic validation of
  PVT trends. Either implement the mirrored Bo-style check (min at Pb) as the docstring promises, or have the
  command output clearly state "density trend validation not yet implemented" instead of a blanket pass.

---

## SECTION F — Security Issues

| # | Severity | File:Line | Issue | Fix |
|---|----------|-----------|-------|-----|
| F1 | Low | `config.py:34-35` | Bot token embedded directly in `TELEGRAM_API_BASE`/`TELEGRAM_FILE_BASE` URLs used for every HTTP call | Already mitigated by `TokenRedactionFilter` (`logging_config.py:27-69`) and `_redact_token` in `telegram_service.py:40-42` — confirm these are applied to **all** log call sites (they currently are); no further action required beyond keeping this discipline as new code is added |
| F2 | Low | `services/ai_service.py:65` | `GROQ_API_KEY` sent as a bearer header — fine — but the key itself is never redacted in logs the way the Telegram token is (no `AIService`-specific redaction filter) | Extend `TokenRedactionFilter` (or add a second filter) to also redact `Bearer <key>` patterns, in case a future `logger.debug` of request headers is added |
| F3 | Info | `handlers/file_handlers.py` | Uploaded files are extracted (PDF/DOCX/XLSX/CSV) with no sandboxing beyond library-level parsing; large/malicious files rely entirely on `pypdf`/`python-docx`/`openpyxl`'s own robustness | Acceptable given `MAX_UPLOAD_SIZE` cap (`config.py:85`) for documents; extend the same cap to photos (see A4) |
| F4 | Info | No rate limiting per chat_id anywhere in `main.py`/`handlers/` | A single user can spam `/calc`, `/estimate`, file uploads, or free-text (each triggering a Groq API call) with no per-chat throttle | Add a simple per-chat_id token bucket / cooldown before invoking `ai.ask_text`/`ai.ask_vision`, to bound cost and abuse |

No SQL, no shell execution of user input, no `eval`/`exec` of user-controlled strings were found anywhere in the reviewed code — this is a genuinely clean area overall.

---

## SECTION G — Performance Issues

| # | Severity | File:Line | Issue | Fix |
|---|----------|-----------|-------|-----|
| G1 | Medium | `services/ai_service.py:97-210` | Full engineering knowledge base (all of `KNOWLEDGE_BASE`, `PVT_PLOT_RULES`, `EXACT_FORMULAS`, `CORRELATIONS`) is serialized into one large string once, then resent as a full message on **every single** `ask_text`/`ask_vision` call (lines 246, 365) — this multiplies input-token cost by the number of chat turns for no benefit after the first turn of a conversation | Send the engineering context once per conversation (cache per `chat_id` whether it was already sent, or fold a condensed version permanently into the system prompt file instead of re-deriving it at runtime) |
| G2 | Low | `main.py:552-577` | Main loop always sleeps `POLLING_LOOP_SLEEP=1.0s` between `get_updates` calls even though `get_updates` itself already long-polls for up to 30s — this adds a needless flat 1s of latency to every incoming message, all day, every day | Reduce/remove `POLLING_LOOP_SLEEP` when the previous call returned no updates (only needed as a fallback with a much lower value, e.g. 0.1-0.25s) |
| G3 | Low | `services/telegram_service.py:191-243` | `send_message` sleeps `POLLING_OFFSET_SLEEP=0.35s` **after every chunk**, including single-chunk (short) messages that don't need any rate-limit protection — adds latency to the common case | Only sleep between **multiple** chunks of the same message (`if len(chunks) > 1`), not after the last/only chunk |
| G4 | Low | A3 (memory leak) also belongs here — unbounded `FILE_CONTEXT`/`IMAGE_CONTEXT` growth degrades long-running process memory footprint over time | See A3 fix |

---

## SECTION H — Recommended Fixes (priority order)

1. **[Deploy]** Remove `healthcheckPath`/`healthcheckTimeout` from `railway.toml` (B2/C1) — single highest-leverage fix for the reported 409s.
2. **[Deploy]** Raise `STARTUP_DELAY` to ≥45s (or make the poll loop interruptible) (B1/C2).
3. **[Deploy]** Change `restartPolicyType` to `"ON_FAILURE"` (C3).
4. **[Bug]** Wire `/analyze` and `/graph` through to the AI path in `main.py`'s dispatch block (A1) — currently completely broken.
5. **[Engineering]** Fix `bo_standing`'s spurious outer `** 0.5` (E1) — every `/estimate bo_standing` result is wrong today.
6. **[Engineering]** Fix or remove `pb_vasquez_beggs`/`rs_vasquez_beggs` (E2) — currently mislabeled, not the real correlation, and silently drops the `p_sep` input.
7. **[Code Quality]** Delete the dead duplicate `HELP_MESSAGE` block (A2).
8. **[AI Quality]** Fix the AI response cache key so it can't collide across different user questions (D1).
9. **[Memory]** Add eviction for `FILE_CONTEXT`/`IMAGE_CONTEXT` and delete stale temp image files proactively (A3/G4).
10. **[Hardening]** Add the missing photo upload size check (A4), extend token redaction to the Groq key (F2), and add basic per-chat rate limiting (F4).

No code has been modified as part of this audit, per your instruction. Ready to proceed with fixes in the
order above (or any order you prefer) on your go-ahead.
