# Petroleum Engineering Telegram Bot

**Professional PVT Lab | Reservoir Engineering | Simulation (Eclipse/CMG) | Drilling | Production | Economics**

A production-quality Telegram bot that combines deterministic petroleum engineering calculations with AI-assisted analysis. Built for petroleum engineers, PVT specialists, and reservoir simulation professionals.

## Architecture

```
petroleum-engineering-bot/
├── main.py                  # Entry point, polling loop, message routing
├── config.py                # Environment variables, API config, plot settings
├── constants.py             # PVT rules, formulas, correlations, knowledge base
├── logging_config.py        # Structured logging setup
├── models/
│   └── pvt_models.py        # Typed data models (TypedDict, dataclass)
├── prompts/
│   └── system_prompt.txt    # AI system prompt (engineering identity)
├── services/
│   ├── ai_service.py        # Groq API client with retry, caching, rate limiting
│   ├── telegram_service.py  # Telegram Bot API client with connection pooling
│   ├── pvt_engine.py        # PVT calculations, trend validation, classification
│   ├── calculation_engine.py # Exact formulas and correlation wrapper
│   ├── file_processing.py   # PDF, DOCX, Excel, CSV extraction
│   ├── visualization.py     # User-supplied-data plot generation (matplotlib)
│   ├── engineering_case.py # Deterministic case serialization and replay
│   └── engineering_report.py# Engineering Case Report V1
├── handlers/
│   ├── command_registry.py  # Decorator-based command dispatch
│   ├── text_handlers.py     # All text command handlers
│   ├── file_handlers.py     # Document and photo upload handlers
│   └── error_handlers.py    # Structured error handling
├── templates/
│   └── pvt_report.txt        # Legacy template/reference only

├── requirements.txt         # Python dependencies
├── Procfile                 # Railway deployment entry
├── railway.toml             # Railway configuration
├── .env.example             # Environment variable template
└── .gitignore
```

## Features

### Deterministic Commands (No AI Hallucination)

| Command | Description | Example |
|---------|-------------|---------|
| `/classify gor=<val> api=<val>` | Fluid classification | `/classify gor=500 api=35` |
| `/calc <type> key=value...` | Exact formulas | `/calc ooip area=500 h=50 phi=0.2` |
| `/estimate <type> key=value...` | Correlation estimates | `/estimate pb_standing rs=650 gas_sg=0.75` |
| `/convert <val> <from> to <to>` | Unit conversion | `/convert 5000 psi to bar` |
| `/plot <type> p=... v=...` | User-supplied-data PNG plot | `/plot bo p=500,1000 v=1.15,1.20` |
| `/check <rel> p=... v=...` | Deterministic trend validation | `/check rs p=500,1000 v=300,300` |
| `/calc vlp ...` | Beggs-Brill VLP calculation | `/calc vlp thp=100 tvd=8000 ...` |
| `/calc nodal ...` | Deterministic IPR–VLP operating point | `/calc nodal model=linear ...` |
| `/calc sensitivity ...` | Deterministic scenario sweep | `/calc sensitivity type=thp ...` |
| `/calc optimize ...` | Constrained candidate comparison | `/calc optimize type=thp ...` |
| `/calc system ...` | Integrated IPR–VLP–choke operating point | `/calc system model=linear ...` |
| `/calc gas_lift ...` | Gas-Lift V1 steady-state screen | `/calc gas_lift ...` |
| `/calc choke ...` | Gilbert 1954 choke calculation | `/calc choke ...` |
| `/pvto /pvdo /pvtg /pvdg` | Simulation table guidance/skeletons | `/pvto` |
| `/export_sim <fluid_type>` | Simulator-selection guidance | `/export_sim gas condensate` |
| `/eclipse` | Eclipse guidance | `/eclipse` |
| `/cmg` | CMG guidance | `/cmg` |

### AI-Assisted and Case Commands

| Command | Description |
|---------|-------------|
| `/analyze` | Analyze an uploaded document or image; AI interpretation is not a substitute for deterministic calculations |
| `/report` | Generate a PVT report only from uploaded/extracted context; refuses to fabricate missing laboratory data |
| `/calc system ... case=1` | Save a deterministic Engineering Case |
| `/case report <case_id>` | Display the saved Engineering Case Report V1 |
| `/case replay <case_id>` | Re-run the case and compare its result deterministically |
| `/case json <case_id>` | Display the serialized Engineering Case |
| `/reset` | Clear uploaded files and session context |

### File Support

| Format | Features |
|--------|----------|
| PDF | Text extraction (pypdf/PyPDF2), auto-segmentation |
| DOCX | Paragraph and table extraction |
| Excel | Multi-sheet data extraction |
| CSV | Auto-delimiter detection |
| PNG/JPG/WebP | Vision AI analysis |

## Engineering Capabilities

### PVT Trend Validation (BLOCK 5)

The bot validates PVT data against physical ground truth rules:

- **Bo vs P**: Peaks at Pb, decreases on both sides
- **Rs vs P**: Constant above Pb, decreases below Pb
- **Bg vs P**: Hyperbolic decrease
- **Z-factor**: U-shaped curve
- **Oil Viscosity**: Mirror of Bo (minimum at Pb)
- **Liquid Dropout**: 0% above Pd, rises then falls
- **CGR**: Constant above Pd, decreases below Pd
- **Relative Volume**: Gentle above Pb, steep below Pb

### Supported Formulas

- OOIP, OGIP, Recovery Factor
- Darcy's Law (radial, linear)
- Productivity Index
- Hydrostatic Pressure
- Mud Weight Required, ECD
- Water Cut, WOR, GOR
- NPV

### Supported Correlations

- Standing (Pb, Rs, Bo)
- Vasquez-Beggs (Pb, Rs)
- Standing-Katz (Z-factor)

### Simulation Support

| Fluid Type | Table | Simulator |
|------------|-------|-----------|
| Black Oil (Rs>0) | PVTO | Eclipse E100 |
| Dead Oil (Rs~0) | PVDO | Eclipse E100 |
| Gas Condensate | PVTG | Eclipse E100/E300 |
| Dry Gas | PVDG | Eclipse E100 |
| Near-Critical | EOS | Eclipse E300 / CMG GEM |

## Deployment

### Railway

1. Connect GitHub repository to Railway
2. Add environment variables:
   - `TELEGRAM_BOT_TOKEN` (from @BotFather)
   - `OPENAI_API_KEY` (Groq API key)
3. Railway auto-detects Python and uses `Procfile`
4. Bot starts automatically on deploy

### Local Development

```bash
# Clone
git clone https://github.com/jha68754-sys/petroleum-engineering-bot.git
cd petroleum-engineering-bot

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your tokens

# Run
python main.py
```

## Technical Details

- **Python**: 3.11+
- **Telegram API**: Long-polling (no webhooks)
- **AI Backend**: Groq API (OpenAI-compatible)
- **Plots**: matplotlib with dark theme, 150 DPI
- **Logging**: Structured, stdout (Railway-compatible)
- **State**: Per-chat context, persisted offset

## License

MIT
