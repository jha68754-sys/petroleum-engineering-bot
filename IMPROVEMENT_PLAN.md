# Petroleum Engineering Bot — Comprehensive Audit & Improvement Plan

## 1. Executive Summary

The current codebase is a single 2,787-line file (`bot.py`) containing 56 functions, 25 global constants, and a monolithic polling loop. While functional, it has significant architectural, reliability, and maintainability issues. This plan details a complete professional refactor into a modular, production-quality architecture.

## 2. Audit Findings

### 2.1 Critical Issues

| # | Category | Severity | Issue | Location |
|---|----------|----------|-------|----------|
| 1 | Architecture | CRITICAL | Single 2,787-line file — impossible to maintain, test, or extend | `bot.py` (entire file) |
| 2 | State Management | CRITICAL | Global mutable dicts `FILE_CONTEXT` and `IMAGE_CONTEXT` — no per-chat isolation, memory leaks, race conditions | `bot.py` L79-82 |
| 3 | Deployment | CRITICAL | Synchronous blocking `while True` polling loop — blocks Railway health checks, no graceful shutdown | `bot.py` L2274-2787 |
| 4 | API Security | HIGH | `OPENAI_API_KEY` env var used for Groq API — confusing naming, potential security confusion | `bot.py` L67 |
| 5 | Error Handling | HIGH | `send_message` silently swallows exceptions with only logging — user gets no feedback | `bot.py` L1580-1581 |
| 6 | Data Parsing | HIGH | `parse_plot_data_from_text` regex can match wrong numbers (e.g., Pb value in pressure list) | `bot.py` L942-947 |
| 7 | PDF Extraction | MEDIUM | `pypdf` is preferred but NOT in `requirements.txt` — will always fall back to PyPDF2 | `requirements.txt` |
| 8 | Excel Support | MEDIUM | No Excel (.xlsx/.xls) support despite user request — `openpyxl`/`pandas` not installed | `requirements.txt` |
| 9 | Type Safety | MEDIUM | Zero type hints throughout — impossible to catch type errors at static analysis time | `bot.py` (entire file) |
| 10 | Testability | MEDIUM | No tests, no test infrastructure, handlers mixed with business logic | `bot.py` (entire file) |

### 2.2 Medium Issues

| # | Category | Issue |
|---|----------|-------|
| 11 | Performance | `generate_glossary_html` generates ~200 lines of HTML/JS on every first call — slow startup |
| 12 | Performance | No connection pooling for Telegram API — new HTTP connection per request |
| 13 | Performance | `send_message` sleeps 0.35s between chunks — slow for long responses |
| 14 | Reliability | `download_file` returns temp file that may not be cleaned up on error |
| 15 | Reliability | `offset` variable is module-level — resets to 0 on Railway restart, causing duplicate updates |
| 16 | Code Quality | 18 `is_*_cmd` one-liner functions that add no value — should be a single dispatch table |
| 17 | Code Quality | Command handler `if/elif` chain is 400+ lines — should be a command registry |
| 18 | Code Quality | `generate_glossary_html` is 198 lines of inline CSS/JS — should be a template file |
| 19 | Code Quality | `SYSTEM_PROMPT` is 168 lines of inline string — should be a separate file |
| 20 | Code Quality | No input validation for user-provided numbers (negative pressures, zero division) |
| 21 | Documentation | README is a single line — no setup, architecture, or usage documentation |
| 22 | Documentation | No docstrings on 30+ functions |
| 23 | Configuration | Model names, API URLs, and limits hardcoded — not configurable |
| 24 | PVT Engineering | Only 2 correlations (Standing for Pb and Rs) — missing Vasquez-Beggs, Standing Bo, Kartoatmodjo, etc. |
| 25 | PVT Engineering | `generate_pvt*_skeleton` returns plain text — should generate actual Eclipse-format data files |

### 2.3 Missing Features

| Feature | Description |
|---------|-------------|
| Excel import/export | Parse .xlsx/.xls files for PVT data |
| CMG table generation | Generate PVT tables in CMG format |
| EOS tuning helper | Guide users through EOS tuning workflow |
| Report PDF export | Generate PDF PVT reports, not just text |
| Conversation history | Store and reuse conversation context for follow-up questions |
| Multi-language prompt | Separate Arabic and English prompt versions |

## 3. Proposed Architecture

```
petroleum-engineering-bot/
├── main.py                    # Entry point, polling loop, graceful shutdown
├── config.py                  # Environment variables, constants, model config
├── constants.py               # All domain constants (PVT rules, formulas, etc.)
├── logging_config.py          # Structured logging setup
├── handlers/
│   ├── __init__.py
│   ├── command_registry.py    # Command dispatch table
│   ├── text_handlers.py       # Text message handlers
│   ├── file_handlers.py       # Document/photo upload handlers
│   └── error_handlers.py      # Error handling utilities
├── services/
│   ├── __init__.py
│   ├── telegram_service.py    # Telegram API client (send, download, polling)
│   ├── ai_service.py          # AI/LLM client (text + vision, retries, caching)
│   ├── pvt_engine.py          # PVT calculations, correlations, trend validation
│   ├── calculation_engine.py  # Exact formulas and unit conversions
│   ├── file_processing.py     # PDF, DOCX, Excel, CSV extraction
│   ├── visualization.py       # Matplotlib PVT plot generation
│   ├── glossary.py            # HTML glossary generation
│   └── simulation.py          # PVTO/PVDO/PVTG/PVDG generation + CMG
├── prompts/
│   ├── system_prompt.txt      # Main system prompt
│   ├── graph_prompt.txt       # Graph analysis prompt
│   └── report_template.txt    # PVT report template
├── models/
│   ├── __init__.py
│   └── pvt_models.py          # Data models (TypedDict/NamedTuple for PVT data)
├── templates/
│   ├── glossary.html          # Glossary HTML template
│   └── pvt_report.txt         # PVT report template
├── requirements.txt           # All dependencies pinned
├── Procfile                   # Railway process definition
├── railway.toml               # Railway config
├── runtime.txt                # Python version
└── README.md                  # Full documentation
```

## 4. Improvement Details

### 4.1 Modular Architecture (Goal 1)

**Split `bot.py` into 15+ modules:**
- `config.py`: All environment variables, API URLs, model names, timeouts
- `constants.py`: SYSTEM_PROMPT, KNOWLEDGE_BASE, FLUID_CLASSIFICATION_TABLE, PVT_PLOT_RULES, etc.
- `services/telegram_service.py`: Telegram API client with connection pooling
- `services/ai_service.py`: AI client with retry logic, rate limiting, caching
- `services/pvt_engine.py`: All PVT calculations, correlations, trend checking
- `services/calculation_engine.py`: Exact formulas, unit conversions
- `services/file_processing.py`: PDF, DOCX, Excel, CSV extraction
- `services/visualization.py`: Matplotlib plot generation
- `services/simulation.py`: PVTO/PVDO/PVTG/PVDG/CMG generation
- `handlers/command_registry.py`: Command dispatch via decorator pattern
- `handlers/text_handlers.py`: Text message command handlers
- `handlers/file_handlers.py`: Document/photo upload handlers
- `models/pvt_models.py`: Typed data models for PVT data
- `prompts/system_prompt.txt`: System prompt as separate file

### 4.2 Reliability (Goal 2)

**Error Handling:**
- Wrap every external API call with proper exception hierarchy
- Add user-facing error messages for all failure modes
- Implement graceful degradation (AI down → deterministic mode still works)
- Add circuit breaker pattern for AI API calls
- Implement proper temp file cleanup with context managers

**Input Validation:**
- Validate all numeric inputs (positive pressures, valid ranges)
- Validate file types and sizes before processing
- Sanitize user text before passing to AI
- Add rate limiting per chat_id

**Structured Logging:**
- JSON-structured logging for production
- Log levels: DEBUG (dev), INFO (production), WARNING (errors), ERROR (failures)
- Log correlation IDs per chat session
- Log API call durations for performance monitoring

### 4.3 Performance (Goal 3)

**Optimizations:**
- Use `requests.Session` with connection pooling for Telegram API
- Cache AI responses for identical questions (LRU cache)
- Cache glossary HTML after first generation (already done, improve)
- Use `asyncio`-compatible structure (prepare for future async migration)
- Lazy-load matplotlib (only when /plot or /check is called)
- Pre-compile all regex patterns
- Reduce message chunk sleep from 0.35s to 0.1s (Telegram allows 30 msg/sec)

### 4.4 Petroleum Engineering (Goal 4)

**Expanded Correlations:**
- Vasquez-Beggs (Rs, Bo, mu_o)
- Standing (Bo, mu_o)
- Kartoatmodjo-Schmidt (Rs, Bo, mu_o, Bg)
- Lee-Gonzalez-Eakin (gas viscosity)
- Beggs-Robinson (dead/live oil viscosity)
- Petrosky-Farshad (Pb, Rs)
- Al-Marhoun (Pb, Rs)
- Glaso (Pb)
- McCain (Pb, Rs)
- Standing (Z-factor from Standing-Katz)
- Standing-Katz chart approximation
- Hall-Yarborough (Z-factor)
- Dranchuk-Abou-Kassem (Z-factor)
- Sutton (gas properties)

**Trend Validation:**
- Expand check to cover ALL PVT relationships in BLOCK 5
- Add statistical outlier detection
- Add data consistency checks (e.g., Bo vs Rs correlation)

**Simulation Tables:**
- Generate actual Eclipse-format PVTO/PVDO/PVTG/PVDG data files
- Generate CMG-format tables
- Auto-detect fluid type and recommend appropriate table
- Validate separator test correction

### 4.5 AI System Prompt (Goal 5)

**Improvements:**
- Move to separate `prompts/system_prompt.txt` file
- Add explicit "I am a PVT engineer" persona instructions
- Add anti-hallucination reinforcement with examples
- Add Arabic terminology reinforcement
- Add equation formatting rules
- Add "measured vs calculated" labeling rules
- Add fallback behavior when AI is unavailable

### 4.6 File Processing (Goal 6)

**PDF:**
- Use `pypdf` as primary (add to requirements.txt)
- Fallback to PyPDF2
- Add table detection and extraction using `camelot` or `tabula-py`
- Extract tables from PDFs into structured data

**Excel:**
- Add `openpyxl` for .xlsx reading
- Auto-detect pressure/value columns
- Handle multiple sheets
- Export PVT tables to Excel format

**CSV:**
- Auto-detect delimiters (comma, semicolon, tab)
- Handle headers in Arabic and English
- Validate column names against known PVT property names

### 4.7 Visualization (Goal 7)

**Improvements:**
- Add phase diagram (P-T envelope) generation
- Add Z-factor chart with Standing-Katz overlay
- Add Bo/Rs composite plot
- Add publication-quality output (300 DPI option)
- Add color-blind-friendly palettes
- Add Arabic axis labels support
- Add trend line overlay with correlation fit

### 4.8 Project Quality (Goal 8)

**Type Hints:**
- Add type hints to ALL functions
- Use TypedDict for data models
- Use Protocol for service interfaces

**Documentation:**
- Full docstrings on every function (Google style)
- Module-level docstrings
- Comprehensive README with setup, commands, and architecture
- Architecture diagram

**Best Practices:**
- PEP 8 compliance (verified with `flake8` or `ruff`)
- Line length 88 (Black standard)
- No global mutable state
- Dependency injection pattern
- Single Responsibility Principle per module

### 4.9 Railway Deployment (Goal 9)

**Improvements:**
- Add `Procfile` with proper web worker
- Add `railway.toml` with build/start commands
- Add health check endpoint (simple HTTP server)
- Graceful shutdown on SIGTERM
- Persistent offset storage (JSON file on disk)
- Environment variable documentation
- Docker-ready with `Dockerfile`

### 4.10 GitHub (Goal 10)

**Process:**
- Create `professional-refactor` branch
- Commit in logical chunks (architecture, then services, then handlers)
- Preserve all existing functionality
- Add `.gitignore` for Python
- Update README.md

## 5. Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Breaking existing functionality | Comprehensive testing of each module before integration |
| Railway deployment failure | Keep original bot.py as backup, test locally first |
| AI prompt changes affecting behavior | Version prompts, test with known inputs |
| New dependencies failing on Railway | Pin exact versions, test on same Python version |
| Performance regression | Profile before/after, use lazy loading |

## 6. Implementation Order

1. **Foundation**: config, logging, models, constants
2. **Infrastructure**: telegram_service, ai_service
3. **Core Engine**: pvt_engine, calculation_engine
4. **File Processing**: file_processing, visualization
5. **Simulation**: simulation (PVTO/PVDO/PVTG/PVDG/CMG)
6. **Handlers**: command_registry, text_handlers, file_handlers
7. **Prompts/Templates**: system_prompt, glossary, report
8. **Entry Point**: main.py, deployment config
9. **Testing**: Integration tests, smoke tests
10. **Documentation**: README, architecture docs
