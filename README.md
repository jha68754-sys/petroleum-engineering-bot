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
│   ├── visualization.py     # PVT plot generation (matplotlib)
│   └── glossary.py          # Interactive HTML glossary generator
├── handlers/
│   ├── command_registry.py  # Decorator-based command dispatch
│   ├── text_handlers.py     # All text command handlers
│   ├── file_handlers.py     # Document and photo upload handlers
│   └── error_handlers.py    # Structured error handling
├── templates/
│   ├── pvt_report.txt       # PVT report template
│   └── glossary.html        # Glossary HTML template
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
| `/plot <type> p=... v=...` | PVT plots + PNG | `/plot bo p=500,1000 v=1.15,1.20` |
| `/check <rel> p=... v=...` | Trend validation | `/check rs p=500,1000 v=300,300` |
| `/pvto /pvdo /pvtg /pvdg` | Simulation table skeletons | `/pvto` |
| `/export_sim <fluid_type>` | Simulator selection | `/export_sim gas condensate` |
| `/eclipse` | Eclipse guidance | `/eclipse` |
| `/cmg` | CMG guidance | `/cmg` |

### AI-Assisted Commands

| Command | Description |
|---------|-------------|
| `/glossary` | Interactive HTML glossary (searchable) |
| `/analyze` | Analyze uploaded PVT reports |
| `/graph` | Analyze uploaded engineering charts |
| `/report` | Generate PVT report skeleton |
| `/reset` | Clear uploaded files |

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
