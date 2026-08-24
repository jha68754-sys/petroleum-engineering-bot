# Engineering Assistant Core V2 — Closure Report

## Executive decision

Engineering Assistant Core V2 is **implemented locally and tested** as an integration layer above the released Petroleum Engineering Bot. It adds a serializable Engineering Data Model, a bounded chat-scoped Engineering Session Context, and persistence hooks in the existing Durable Engineering Workspace. It does not add a second calculation engine, a second knowledge base, field-data import, user accounts, uncertainty analysis, or paid infrastructure.

The release is not yet deployable from this session because the managed GitHub connector has read-only access and rejected the write operation with HTTP 403. Therefore the accurate release status is:

> **CORE IMPLEMENTED · TESTED · DEPLOYMENT BLOCKED · PERSISTENCE CROSS-REDEPLOY BLOCKED**

The local commit is ready, but `origin/main` has not advanced and Railway has not received a new deployment trigger.

## Audit and actual gap

The existing bot already contained deterministic petroleum-engineering engines, Knowledge/Q&A V1, immutable canonical Engineering Cases, replay, Case Registry persistence, and Scenario Comparison persistence. The highest-value remaining gap was not another formula. It was the absence of a coherent conversational context layer able to identify the current case, previous cases, the active calculation domain, selected model and PVT context, and safe profile values without guessing.

The audit also confirmed that the SQLite Workspace implementation can persist context and cases on the configured path, but Railway cross-redeploy durability remains unavailable while no Railway Volume or managed database is provisioned. The user’s cost boundary was respected; no paid or credit-consuming storage was created.

## Architecture delivered

The implementation follows one direction of authority. Released deterministic handlers and engines remain responsible for calculation. `EngineeringCase` remains the canonical immutable engineering envelope and deterministic SHA-256 identity. `EngineeringCaseRegistry` remains the existing Workspace persistence abstraction. `EngineeringSessionContext` is a chat-scoped reference layer that points to deterministic case and comparison identities; it does not replace the Case Registry.

| Layer | Delivered behavior | Source of truth |
|---|---|---|
| Engineering Data Model | Optional well, reservoir-fluid, flow, equipment, measurements and traceability sections with explicit value origins | Case inputs, PVT context and calculated result |
| Session Context | Current case, ordered prior cases, current domain, selected model, PVT context, current profile and comparison references | Deterministic cases only |
| Workspace | Session table with canonical JSON, SHA-256 integrity hash and schema version in existing SQLite registry | Existing Registry database |
| Conversation routing | Explicit report, replay, previous/first/current reference, comparison and strict THP override routes | Deterministic context resolver |
| AI boundary | Deterministic context routes bypass AI; unrelated free text preserves Knowledge/Q&A then existing AI fallback | Existing dispatcher policy |

## Engineering Data Model

`EngineeringDataModel` uses optional sections and does not require a complete well model. Every stored value carries an origin: `USER_PROVIDED`, `DEFAULTED`, `CALCULATED`, or `UNKNOWN`. `UNKNOWN` cannot carry a value, so omitted information is never silently inferred. The profile includes traceability to the Case ID, calculation type, model, PVT selectors and schema.

Values are derived only from the released Case envelope. Input fields appearing in the case request are marked user-provided when their aliases are explicitly present; engine defaults remain defaulted when a field has a concrete default; omitted optional fields remain unknown; result metrics are calculated. PVT values retain their explicit PVT provenance and are not synthesized by the session layer.

## Engineering Session Context

The context is bounded by chat and serializable. It records the current deterministic Case ID, an ordered list of prior Case IDs, the current calculation type/domain, selected model controls, PVT mode/model/context, current engineering profile, current comparison ID and prior comparison IDs. Telegram chat identifiers are transformed into a deterministic SHA-256 session key before persistence; the raw chat identifier is not written to the Workspace session table.

Reference resolution is strict. `current`, `previous`, `first`, `same well`, Arabic equivalents, and a full Case ID are supported only when they identify a known context item. Missing current or previous cases produce typed errors. Unknown references produce an ambiguity error. The resolver does not select a case by recency when the user supplied an ambiguous phrase.

The natural-language routes now support explicit forms including `اعطني التقرير`, `اعطني التقرير للحالة السابقة`, `اعمل replay`, `قارنها بالحالة السابقة`, `change THP to 200 psia`, and `غير THP فقط إلى 200 psia`. THP mutation is intentionally narrow: it accepts only an explicit psia value, only for a current replayable Integrated System case, and reuses the released `IntegratedSystemEngine` and Case builder. A Choke case, missing unit, incomplete PVT selector or unsupported calculation type receives a typed clarification rather than an invented calculation.

## Durable Workspace and storage decision

Session persistence reuses `EngineeringCaseRegistry` and its current SQLite connection. It adds `engineering_sessions` with a session key, canonical session JSON, content hash, timestamps and `engineering_session_context_v2` schema version. Reload validates the content hash, schema version, canonical serialization and deterministic IDs. Tampering and schema incompatibility have typed errors.

This is persistence in the existing Workspace abstraction and is verified locally across registry close/reopen. It is **not an assertion of Railway cross-redeploy persistence**. The deployed Railway service has no attached Volume or managed database under the user’s current cost boundary. No storage service, Volume, or paid infrastructure was created.

## Reused, changed and deliberately not changed

| Category | Decision |
|---|---|
| Reused | Existing EngineeringCase, Case Registry, ScenarioComparison, replay adapters, report renderer, released input builders and deterministic engines |
| Changed | New context module; bounded state cache; Registry session table/API; handler save hooks; main dispatcher context route; `/reset` cleanup; `/calc` delegation preserves chat metadata |
| Not changed | Numerical equations, engine contracts, Knowledge V1 dataset, Q&A answer source, AI service behavior for unrelated text, field-data import, artificial-lift expansion, reserves, testing, uncertainty and user accounts |
| Infrastructure | No Railway Volume, database or paid service provisioned |

## AI–engine boundary

The context layer is deterministic and does not ask the AI to identify a case, infer an input, calculate a rate or select between ambiguous cases. Explicit context actions are evaluated before Knowledge/Q&A and before the AI fallback. AI remains available for the existing unrelated free-text behavior. Released engineering engines remain the only calculation authority.

## Validation and replay

The test suite verifies Data Model serialization, value origins, unknown safety, case-derived profiles, context update and ordered history, typed reference errors, session close/reopen, tamper rejection, natural report/replay/comparison routing, no-AI deterministic dispatch, strict THP mutation, and `/calc system` chat-context propagation. Existing Registry and Durable Workspace contracts remain green.

Replay loads the case from the Registry independently of the in-process cache, reconstructs it through the released replay adapter, compares deterministic identity/result behavior, records replay metadata and reports `MATCH` or `DIFFERENT` honestly. A mismatch is never rewritten as a success.

## Test, security and quality results

| Check | Result |
|---|---:|
| Core V2 focused tests | **11 passed** |
| Existing Registry + Durable Workspace tests | **379 passed** |
| Full regression: `tests test_pvt.py test_409_fix.py` | **901 passed in 748.76s** |
| `git diff --check` | **PASS** |
| Core V2 compile check | **PASS** |
| Knowledge JSON validation | **PASS** |
| Secret scan over changed implementation/tests | **PASS** |
| Frozen-engine diff check | **PASS** |
| Full repository `compileall` | **BLOCKED by pre-existing syntax error** in `petroleum_ai/expert_system/engineering_experience.py` (`from __future__:: annotations`), outside this increment and unchanged |

No secret was added to the repository. Credentials sent in chat were not used or stored. They should be revoked or rotated by the account owner.

## Deployment and live acceptance

The implementation is committed locally and the local worktree is clean. The remote branch remains at `f2e67ea97b2357b09098dbe67785c8de877a603d` because the managed GitHub connector rejected both git push and the write API operation with HTTP 403. The connector can read the repository and reports the account, but it does not currently have write permission.

Because the commit has not reached GitHub, Railway has not received a deployment trigger for Core V2. No live Telegram acceptance is claimed for this increment. The prior deployed service remains the last verified Railway release; it does not contain this local Core V2 commit.

## Limitations, blocked dependency and roadmap

The current implementation provides local restart/reopen validation through the SQLite Workspace and a bounded in-memory fast cache. Cross-redeploy persistence is blocked until a durable Railway Volume or managed database is explicitly approved and provisioned. That decision remains outside this increment because the user required free availability and the checked Railway Volume model is usage-metered.

The next safe step is operational rather than architectural: grant the managed GitHub connector `Contents: Read and write`, or push the local commit manually. After GitHub accepts the commit, verify the commit status, wait for Railway automatic deployment, inspect the online deployment, and perform owner-led live Telegram acceptance. Only after paid/credit-consuming storage is explicitly approved should cross-redeploy context persistence be tested on Railway.

## Final status

> **Engineering Assistant Core V2: IMPLEMENTED · TESTED · NOT YET DEPLOYED · PERSISTENCE BLOCKED**

The software layer is ready. The remaining blocker is write access to GitHub, followed by the deployment and live acceptance steps that cannot honestly be claimed until the commit is present on `origin/main`.

## References

[1]: https://github.com/jha68754-sys/petroleum-engineering-bot "Petroleum Engineering Bot repository"
