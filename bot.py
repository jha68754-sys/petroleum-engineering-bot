import os
import re
import time
import base64
import tempfile
import mimetypes
import requests

from PyPDF2 import PdfReader
from docx import Document

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('OPENAI_API_KEY')
TELEGRAM_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'
GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
TEXT_MODEL = os.getenv('GROQ_TEXT_MODEL', 'llama-3.3-70b-versatile')
VISION_MODEL = os.getenv('GROQ_VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')

offset = 0
FILE_CONTEXT = {}
IMAGE_CONTEXT = {}

GLOBAL_PVT_REFERENCE = '''
Professional PVT Engineering Reference System

Role: act as a real PVT laboratory engineer, reservoir fluid specialist, and reservoir simulation engineer.
The reference report is an example for workflow and style only. It is not a rigid template.
Always adapt to sample type, fluid system, reservoir type, available data, lab objective, report scope, client requirements, and simulation objective.

Correct terminology:
PVT = Pressure-Volume-Temperature.
Reservoir = Ø§ÙÙÙÙÙ Reservoir.
Well = Ø§ÙØ¨Ø¦Ø± Well.
Formation = Ø§ÙØªÙÙÙÙ Formation.
Bottom Hole Sample = Ø¹ÙÙØ© ÙØ§Ø¹ Ø§ÙØ¨Ø¦Ø± Bottom Hole Sample.
Surface Separator Oil Sample = Ø¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù Surface Separator Oil Sample.
Separator Gas Sample = Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ Separator Gas Sample.
Stock Tank Oil = Ø²ÙØª Ø§ÙØ®Ø²Ø§Ù Ø§ÙØ³Ø·Ø­Ù Stock Tank Oil.
Recombined Sample = Ø¹ÙÙØ© ÙØ¹Ø§Ø¯ ØªØ±ÙÙØ¨ÙØ§ Recombined Sample.
Recombination = Ø¥Ø¹Ø§Ø¯Ø© ØªØ±ÙÙØ¨ Ø§ÙØ¹ÙÙØ© Recombination.
Bubble Point Pressure = Ø¶ØºØ· ÙÙØ·Ø© Ø§ÙÙÙØ§Ø¹Ø© Bubble Point Pressure.
Dew Point Pressure = Ø¶ØºØ· ÙÙØ·Ø© Ø§ÙÙØ¯Ù Dew Point Pressure.
Bo = ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØ²ÙØª Oil Formation Volume Factor.
Bg = ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØºØ§Ø² Gas Formation Volume Factor.
Rs = ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨ Solution Gas-Oil Ratio.
Rv = ÙØ³Ø¨Ø© Ø§ÙØ²ÙØª Ø§ÙÙØªØ¨Ø®Ø± ÙÙ Ø§ÙØºØ§Ø² Vaporized Oil-Gas Ratio.
GOR = ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª Gas-Oil Ratio.
CGR = ÙØ³Ø¨Ø© Ø§ÙÙÙØ«ÙØ§Øª Ø¥ÙÙ Ø§ÙØºØ§Ø² Condensate-Gas Ratio.
Z-factor = ÙØ¹Ø§ÙÙ Ø§ÙØ§ÙØ­Ø±Ø§Ù Ø§ÙØºØ§Ø²Ù Gas Deviation Factor.
Viscosity = Ø§ÙÙØ²ÙØ¬Ø© Viscosity.
Density = Ø§ÙÙØ«Ø§ÙØ© Density.
Specific Gravity = Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ© Specific Gravity.
API Gravity = Ø¯Ø±Ø¬Ø© API.
CCE = Constant Composition Expansion.
CME = Constant Mass Expansion.
DV = Differential Vaporization / Differential Liberation.
CVD = Constant Volume Depletion.
Separator Test = Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙÙØ§ØµÙ Separator Test.
Flash Test = Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙÙÙÙØ¶ Flash Test.
Compositional Analysis = Ø§ÙØªØ­ÙÙÙ Ø§ÙØªØ±ÙÙØ¨Ù Compositional Analysis.
EOS Tuning = ÙÙØ§Ø¡ÙØ© ÙØ¹Ø§Ø¯ÙØ© Ø§ÙØ­Ø§ÙØ© EOS Tuning.
PVTO = Eclipse black-oil oil PVT table.
PVTG = Eclipse gas PVT table.
CMG PVT Input = ÙØ¯Ø®ÙØ§Øª PVT ÙÙØ­Ø§ÙÙ CMG.

Forbidden terms:
Do not call Bo Ø§ÙØ¶ØºØ· Ø§ÙØ¨ÙÙÙ or Ø§ÙÙØ¹Ø§ÙÙ Ø§ÙØ¨ÙÙÙ.
Do not call Rs Ø§ÙØªØ±Ø´ÙØ­.
Do not call GOR Ø§ÙÙØ³Ø¨Ø© Ø§ÙÙØ¦ÙÙØ© ÙÙØºØ§Ø².
Do not say Ø§ÙÙÙØ²Ø¬ for Viscosity.
Do not say Ø§ÙØ­ÙØ±Ø© for Reservoir.
Do not say Ø§ÙØ³Ø·ÙØ¹ Ø§ÙÙÙØ¹Ù or Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙØ³Ø·ÙØ¹.
Do not define PVT as Pressuring Volume and Temperature.
Do not use vague tests like Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙØ¶ØºØ· ÙØ§ÙØ­Ø±Ø§Ø±Ø© when actual tests are CCE/CME, DV, CVD, Separator Test, Recombination, Compositional Analysis, or Viscosity Test.

Engineering workflow:
1. Bottom Hole Sample: validation, opening pressure/leak check, restoration to reservoir conditions, CCE/CME, DV for oil systems, CVD for gas condensate, Separator Test, Viscosity, Composition, PVT tables and plots.
2. Surface Separator Oil + Separator Gas: surface separated samples do not directly represent original reservoir fluid. Need separator P/T, oil/gas rates, separator GOR or producing GOR, oil and gas composition, API, density, water/emulsion check. Recombine oil and gas, validate recombined fluid, then run CCE/CME, DV or CVD, Separator Test, Viscosity.
3. Black Oil: Bubble Point Pressure, Rs, Bo, Density, Viscosity, DV/Differential Liberation, Separator Test, Stock Tank Oil API, PVTO.
4. Volatile Oil: saturation pressure, high GOR, shrinkage, composition, separator optimization, likely EOS/compositional simulation.
5. Gas Condensate: Dew Point, CVD, liquid dropout, CGR, Z-factor, retrograde condensation, PVTG or compositional/EOS.

Simulation logic:
Use PVTO for black-oil oil systems with pressure-Rs-Bo-viscosity tables.
Use PVTG for gas systems when gas PVT data are available.
Use compositional/EOS for volatile oil, gas condensate, rich gas, miscibility, CO2/H2S, or strong compositional effects.
DV supports black-oil tables. CVD supports gas condensate and EOS work. Separator conditions affect GOR, Bo, Rs, API and simulator surface conditions.

Graph interpretation:
Identify axes and units, trend, non-physical behavior, anomalies, retrograde behavior, contamination indicators, engineering meaning, causes and recommendations.
'''

SYSTEM_PROMPT = '''
You are a professional Petroleum Engineering and PVT Laboratory AI assistant.
Answer like a real PVT engineer, reservoir fluid specialist, and reservoir simulation engineer.
Never give generic textbook answers. Never invent PVT values. Use engineering judgment.
If Arabic: use strong professional Arabic with correct petroleum terms. If English: use professional petroleum engineering English.

For every technical answer:
1. Identify sample type.
2. Identify likely fluid system.
3. Select correct PVT workflow.
4. Explain required lab tests.
5. Explain calculations only if data are available.
6. Explain required plots.
7. Explain simulation relevance.
8. Mention missing data.
9. Give engineering interpretation.

Commands: /analyze, /report, /calc, /plot, /graph, /interpret_graph, /check, /export_sim, /pvto, /pvtg, /eclipse, /cmg.
Formatting: no markdown symbols like ** or ###, no vertical-line tables, clean Telegram text, clear headings.
'''

def fix_terms(text):
    text = str(text)
    repl = {
        'Pressuring Volume and Temperature': 'Pressure-Volume-Temperature',
        'Ø§ÙØ¶ØºØ· Ø§ÙØ¨ÙÙÙ': 'ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ',
        'Ø§ÙÙØ¹Ø§ÙÙ Ø§ÙØ¨ÙÙÙ': 'ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ',
        'Ø§ÙØªØ±Ø´ÙØ­': 'ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨',
        'Ø§ÙÙØ³Ø¨Ø© Ø§ÙÙØ¦ÙÙØ© ÙÙØºØ§Ø²': 'ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª',
        'ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ¦ÙÙØ©': 'ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª',
        'Ø§ÙÙÛØ³ÙÙØ²ÙØ©': 'Ø§ÙÙØ²ÙØ¬Ø©',
        'Ø§ÙÙÙØ²Ø¬': 'Ø§ÙÙØ²ÙØ¬Ø©',
        'Ø§ÙØ­ÙØ±Ø©': 'Ø§ÙÙÙÙÙ',
        'Ø§ÙØ³Ø·ÙØ¹ Ø§ÙÙÙØ¹Ù': 'Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ©',
        'Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙØ³Ø·ÙØ¹': 'Ø§Ø®ØªØ¨Ø§Ø± Ø§ÙÙØ«Ø§ÙØ© Ø§ÙÙÙØ¹ÙØ©',
        'ÙØ­Ù PVT': 'ÙÙØ­ÙÙØ§Øª PVT',
        'Ø§ÙÙÙÙØ°Ø¬ Ø§ÙØ¨ÙÙÙ': 'Black Oil Model Ø£Ù Compositional Model',
        'Ø§ÙÙÙÙØ°Ø¬ Ø§ÙÙØ¶ØºÙØ·': 'Black Oil Model Ø£Ù Compositional Model',
        'Volume Expansion Factor': 'Oil Formation Volume Factor',
        'Bo (Volume Expansion Factor)': 'Bo ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØ²ÙØª Oil Formation Volume Factor',
        'Bo Volume Expansion Factor': 'Bo ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØ²ÙØª Oil Formation Volume Factor',
        'Rs (Solution Gas-Oil Ratio)': 'Rs ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨ Solution Gas-Oil Ratio',
        'GOR Ø§ÙÙØ³Ø¨Ø©': 'GOR ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª',
        'Ø§ÙØ¶ØºØ· Ø§ÙØ¨Ø§ÙØº': 'Ø¶ØºØ· Ø§ÙØªØ´Ø¨Ø¹ Ø£Ù Ø¶ØºØ· Ø§ÙØ§Ø®ØªØ¨Ø§Ø± Ø­Ø³Ø¨ Ø§ÙØ³ÙØ§Ù',
        'Ø§ÙØ­Ø±Ø§Ø±Ø© Ø§ÙØ¨Ø§ÙØºØ©': 'Ø¯Ø±Ø¬Ø© Ø­Ø±Ø§Ø±Ø© Ø§ÙÙÙÙÙ Ø£Ù Ø¯Ø±Ø¬Ø© Ø­Ø±Ø§Ø±Ø© Ø§ÙØ§Ø®ØªØ¨Ø§Ø± Ø­Ø³Ø¨ Ø§ÙØ³ÙØ§Ù',
    }
    for a, b in repl.items():
        text = text.replace(a, b)
    return text

def clean_text(text):
    text = fix_terms(text)
    for s in ['**', '###', '##', '#', '|', '[', ']']:
        text = text.replace(s, ' ' if s == '|' else '')
    return text.strip()

def send_message(chat_id, text):
    text = clean_text(text)
    if len(text) <= 3900:
        requests.post(f'{TELEGRAM_URL}/sendMessage', data={'chat_id': chat_id, 'text': text})
    else:
        for i in range(0, len(text), 3900):
            requests.post(f'{TELEGRAM_URL}/sendMessage', data={'chat_id': chat_id, 'text': text[i:i+3900]})
            time.sleep(0.5)

def send_photo(chat_id, photo_path, caption=''):
    with open(photo_path, 'rb') as photo:
        requests.post(f'{TELEGRAM_URL}/sendPhoto', data={'chat_id': chat_id, 'caption': caption}, files={'photo': photo})

def surface_separator_analysis_ar():
    return '''
ØªØ­ÙÙÙ ÙÙØ¯Ø³Ù ÙØ¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù ÙØ¹ Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ

ÙÙØ¹ Ø§ÙØ¹ÙÙØ§Øª
Ø§ÙØ¹ÙÙØ§Øª Ø§ÙÙØ°ÙÙØ±Ø© ÙÙ Ø¹ÙÙØ§Øª Ø³Ø·Ø­ÙØ© ÙÙÙØµÙØ©:
- Surface Separator Oil Sample: Ø¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù.
- Separator Gas Sample: Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ.

ÙØ°Ù Ø§ÙØ¹ÙÙØ§Øª ÙØ§ ØªÙØ«Ù Ø³Ø§Ø¦Ù Ø§ÙÙÙÙÙ Ø§ÙØ£ØµÙÙ ÙØ¨Ø§Ø´Ø±Ø© ÙØ«Ù Ø¹ÙÙØ© ÙØ§Ø¹ Ø§ÙØ¨Ø¦Ø± Bottom Hole SampleØ ÙØ£Ù Ø§ÙØºØ§Ø² ÙØ§ÙØ²ÙØª Ø§ÙÙØµÙØ§ Ø¹ÙØ¯ Ø¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù. ÙØ°ÙÙ ÙØ§ ÙÙÙÙ Ø¨ÙØ§Ø¡ Ø³ÙÙÙ PVT ÙØ§ÙÙ ÙÙÙÙÙÙ ÙÙÙØ§ ÙØ¨Ø§Ø´Ø±Ø© Ø¥ÙØ§ Ø¨Ø¹Ø¯ Ø¥Ø¹Ø§Ø¯Ø© ØªØ±ÙÙØ¨ Ø§ÙØ¹ÙÙØ© Recombination Ø¨Ø·Ø±ÙÙØ© ØµØ­ÙØ­Ø©.

Ø§ÙÙÙØ±Ø© Ø§ÙÙÙØ¯Ø³ÙØ© Ø§ÙØ£Ø³Ø§Ø³ÙØ©
Ø§ÙÙØ¯Ù ÙÙ Ø¥Ø¹Ø§Ø¯Ø© Ø¨ÙØ§Ø¡ Ø³Ø§Ø¦Ù Ø§ÙÙÙÙÙ Ø§ÙØ£ØµÙÙ ØªÙØ±ÙØ¨ÙØ§Ù ÙÙ Ø®ÙØ§Ù Ø¹ÙÙØ© Ø§ÙØ²ÙØª Ø§ÙØ³Ø·Ø­ÙØ©Ø Ø¹ÙÙØ© Ø§ÙØºØ§Ø² Ø§ÙÙÙÙØµÙØ Ø¸Ø±ÙÙ Ø§ÙÙØ§ØµÙØ ÙÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª GOR Ø£Ù ÙØ¹Ø¯ÙØ§Øª Ø§ÙØ¥ÙØªØ§Ø¬. Ø¨Ø¹Ø¯ Ø°ÙÙ ØªÙØ¬Ø±Ù Ø§Ø®ØªØ¨Ø§Ø±Ø§Øª PVT Ø¹ÙÙ Ø§ÙØ¹ÙÙØ© Ø§ÙÙØ¹Ø§Ø¯ ØªØ±ÙÙØ¨ÙØ§ Recombined Sample.

Ø§ÙØ¨ÙØ§ÙØ§Øª Ø§ÙÙØ·ÙÙØ¨Ø©
1. Ø¨ÙØ§ÙØ§Øª Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù:
- Separator Pressure Ø¶ØºØ· Ø§ÙÙØ§ØµÙ.
- Separator Temperature Ø¯Ø±Ø¬Ø© Ø­Ø±Ø§Ø±Ø© Ø§ÙÙØ§ØµÙ.
- Ø¹Ø¯Ø¯ ÙØ±Ø§Ø­Ù Ø§ÙÙØµÙ Ø¥Ù ÙØ¬Ø¯Øª.
- Stock Tank Conditions Ø¥Ù ÙØ¬Ø¯Øª.

2. Ø¨ÙØ§ÙØ§Øª Ø§ÙØ¥ÙØªØ§Ø¬:
- Oil Rate ÙØ¹Ø¯Ù Ø¥ÙØªØ§Ø¬ Ø§ÙØ²ÙØª.
- Gas Rate ÙØ¹Ø¯Ù Ø¥ÙØªØ§Ø¬ Ø§ÙØºØ§Ø².
- Producing GOR Ø£Ù Separator GOR ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø¥ÙÙ Ø§ÙØ²ÙØª.
- Water Cut Ø£Ù ÙØ¬ÙØ¯ ÙØ§Ø¡/ÙØ³ØªØ­ÙØ¨ Ø¥Ù ÙØ¬Ø¯.

3. Ø¨ÙØ§ÙØ§Øª Ø§ÙØ¹ÙÙØ§Øª:
- Ø­Ø¬Ù Ø¹ÙÙØ© Ø§ÙØ²ÙØª.
- Ø¶ØºØ· ÙØ¯Ø±Ø¬Ø© Ø­Ø±Ø§Ø±Ø© Ø£Ø®Ø° Ø§ÙØ¹ÙÙØ©.
- Separator Gas Composition ØªØ±ÙÙØ¨ Ø§ÙØºØ§Ø².
- Stock Tank Oil Composition Ø£Ù ØªØ±ÙÙØ¨ Ø§ÙØ²ÙØª.
- Oil Density ÙØ«Ø§ÙØ© Ø§ÙØ²ÙØª.
- API Gravity.
- Gas Specific Gravity.
- H2S Ù CO2 Ø¥Ù ÙØ¬Ø¯Øª.

Ø§ÙØ§Ø®ØªØ¨Ø§Ø±Ø§Øª Ø§ÙÙØ·ÙÙØ¨Ø©
1. Compositional Analysis Ø§ÙØªØ­ÙÙÙ Ø§ÙØªØ±ÙÙØ¨Ù:
ØªØ­ÙÙÙ Ø§ÙØºØ§Ø² C1 Ø¥ÙÙ C7+ ÙØ¹ CO2 Ù N2 Ù H2SØ ÙØªØ­ÙÙÙ Ø§ÙØ³Ø§Ø¦Ù ÙØªÙØµÙÙ C7+ Ø£Ù C12+ Ø­Ø³Ø¨ Ø§ÙÙØ®ØªØ¨Ø±.

2. Recombination Ø¥Ø¹Ø§Ø¯Ø© ØªØ±ÙÙØ¨ Ø§ÙØ¹ÙÙØ©:
Ø®ÙØ· Ø²ÙØª Ø§ÙÙØ§ØµÙ ÙØ¹ ØºØ§Ø² Ø§ÙÙØ§ØµÙ Ø¨ÙØ³Ø¨Ø© ÙÙØ§Ø³Ø¨Ø© Ø§Ø¹ØªÙØ§Ø¯Ø§Ù Ø¹ÙÙ Producing GOR Ø£Ù Separator GOR Ø£Ù ÙØ¹Ø¯ÙØ§Øª Ø§ÙØ²ÙØª ÙØ§ÙØºØ§Ø² ÙØ¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ.

3. Validation of Recombined Fluid:
Ø§ÙØªØ£ÙØ¯ ÙÙ Ø§Ø³ØªÙØ±Ø§Ø± Ø§ÙØ¹ÙÙØ©Ø Ø¹Ø¯Ù ÙÙØ¯Ø§Ù Ø§ÙØºØ§Ø²Ø ÙØªÙØ§ÙÙ Ø¶ØºØ· Ø§ÙØªØ´Ø¨Ø¹ Ø§ÙÙØªÙÙØ¹ ÙØ¹ Ø§ÙØ¨ÙØ§ÙØ§Øª Ø§ÙØ­ÙÙÙØ© Ø¥Ù ÙØ¬Ø¯Øª.

4. CCE Ø£Ù CME:
ÙØªØ­Ø¯ÙØ¯ Bubble Point Pressure Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙÙØ¸Ø§Ù Ø²ÙØªÙØ Ø£Ù Dew Point Pressure Ø¥Ø°Ø§ ÙØ§Ù ØºØ§Ø²ÙØ§Ù ÙÙØ«ÙØ§ÙØ ÙØ¹ Relative Volume Ù Y-Function Ù Compressibility.

5. DV Differential Vaporization:
ÙÙØ§Ø³Ø¨ ØºØ§ÙØ¨Ø§Ù ÙÙ Black Oil Ø£Ù Volatile OilØ ÙÙØ¹Ø·Ù Rs Ù Bo ÙØ§ÙÙØ«Ø§ÙØ© Ù Gas Gravity Ù Z-factor Ù Bg.

6. CVD Constant Volume Depletion:
ÙØ³ØªØ®Ø¯Ù Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙÙØ¸Ø§Ù Gas CondensateØ ÙÙØ¹Ø·Ù Liquid Dropout Ù Retrograde Condensation Ù CGR Ù Z-factor.

7. Separator Test:
ÙÙÙ Ø¬Ø¯Ø§Ù ÙØ£Ù Ø§ÙØ¹ÙÙØ© Ø£ØµÙÙØ§ ÙÙ Ø§ÙØ³Ø·Ø­Ø ÙÙØ¹Ø·Ù Separator GOR Ù Stock Tank Oil properties Ù Surface shrinkage ÙØªØ£Ø«ÙØ± Ø¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ Ø¹ÙÙ Bo Ù Rs Ù API.

8. Viscosity Test:
ÙÙØ§Ø³ Oil Viscosity Ù Gas Viscosity Ø¹ÙØ¯ Ø§ÙØ­Ø§Ø¬Ø© ÙÙÙ ÙØªØ­Øª Ø¶ØºØ· Ø§ÙØªØ´Ø¨Ø¹.

Ø§ÙØ­Ø³Ø§Ø¨Ø§Øª Ø§ÙØµØ­ÙØ­Ø©
ÙØ§ ÙØªÙ Ø­Ø³Ø§Ø¨ ÙÙÙ ÙÙØ§Ø¦ÙØ© Ø¨Ø¯ÙÙ Ø¨ÙØ§ÙØ§Øª Ø±ÙÙÙØ©Ø ÙÙÙ Ø§ÙØ­Ø³Ø§Ø¨Ø§Øª Ø§ÙÙØ·ÙÙØ¨Ø© Ø¹Ø§Ø¯Ø© ÙÙ:
- Recombination Ratio.
- Total GOR.
- Rs ÙØ³Ø¨Ø© Ø§ÙØºØ§Ø² Ø§ÙÙØ°Ø§Ø¨.
- Bo ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØ²ÙØª.
- Bg ÙØ¹Ø§ÙÙ Ø­Ø¬Ù Ø§ÙØªÙÙÙÙ ÙÙØºØ§Ø².
- Oil Density.
- Gas Specific Gravity.
- API Gravity.
- Z-factor.
- Oil and Gas Viscosity.
- Compressibility.
- Y-Function.

Ø§ÙÙÙØ­ÙÙØ§Øª Ø§ÙÙØ·ÙÙØ¨Ø©
ÙÙØ²ÙØª:
- Pressure vs Bo.
- Pressure vs Rs.
- Pressure vs Oil Viscosity.
- Pressure vs Oil Density.
- Pressure vs Relative Volume.
- Pressure vs Y-Function.

ÙÙØºØ§Ø²:
- Pressure vs Z-factor.
- Pressure vs Bg.
- Pressure vs Gas Viscosity.

ÙÙ Gas Condensate:
- Pressure vs Liquid Dropout.
- Pressure vs CGR.
- Phase Envelope Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙØªØ±ÙÙØ¨ ÙØªÙÙØ±.

Ø¥Ø¹Ø¯Ø§Ø¯ Ø§ÙØ¨ÙØ§ÙØ§Øª ÙÙÙØ­Ø§ÙØ§Ø© Eclipse Ø£Ù CMG
Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙØ³Ø§Ø¦Ù Black Oil: Ø§ÙØ£ÙØ¶Ù ØªØ¬ÙÙØ² PVTO ÙÙ Eclipse Ø¨Ø§Ø³ØªØ®Ø¯Ø§Ù Pressure, Rs, Bo, Oil ViscosityØ ÙØ¹ PVTG ÙÙØºØ§Ø² Ø¥Ø°Ø§ ÙØ²Ù.
Ø¥Ø°Ø§ ÙØ§Ù Ø§ÙØ³Ø§Ø¦Ù Volatile Oil Ø£Ù Gas Condensate: Ø§ÙØ£ÙØ¶Ù Ø§Ø³ØªØ®Ø¯Ø§Ù Compositional Model ÙØ¹ EOS Tuning ÙÙ CMG GEM Ø£Ù Eclipse Compositional.

ØªØ­Ø°ÙØ±Ø§Øª ÙÙØ¯Ø³ÙØ© ÙÙÙØ©
- ÙØ§ ØªÙØ³ØªØ®Ø¯Ù Ø¹ÙÙØ§Øª Ø§ÙØ³Ø·Ø­ ÙØ¨Ø§Ø´Ø±Ø© ÙØ£ÙÙØ§ Ø¹ÙÙØ© ÙÙÙÙ.
- ÙØ¬Ø¨ Ø¥Ø¬Ø±Ø§Ø¡ Recombination ÙØ¨Ù Ø§ÙØ­ÙÙ Ø§ÙÙÙØ§Ø¦Ù Ø¹ÙÙ Ø³ÙÙÙ Ø§ÙÙÙÙÙ.
- ÙÙÙ Bo Ù Rs Ù Bubble Point Pressure ÙØ§ ØªÙØ³ØªÙØªØ¬ Ø¨Ø¯ÙØ© ÙÙ Ø§ÙØ³Ø·Ø­ Ø¨Ø¯ÙÙ Ø¥Ø¹Ø§Ø¯Ø© ØªØ±ÙÙØ¨ ÙØ§Ø®ØªØ¨Ø§Ø± PVT.
- Ø¸Ø±ÙÙ Ø§ÙÙØ§ØµÙ ØªØ¤Ø«Ø± ÙØ¨Ø§Ø´Ø±Ø© Ø¹ÙÙ GOR Ù API Ù Stock Tank Properties.
- Ø§Ø®ØªÙØ§Ø± Black Oil Model Ø£Ù Compositional Model ÙØ¹ØªÙØ¯ Ø¹ÙÙ ÙÙØ¹ Ø§ÙØ³Ø§Ø¦Ù ÙØ§ÙÙØ¯Ù ÙÙ Ø§ÙÙØ­Ø§ÙØ§Ø©.

Ø§ÙØ®ÙØ§ØµØ© Ø§ÙÙÙØ¯Ø³ÙØ©
Ø§ÙØ¹ÙÙØªØ§Ù ØªÙØ«ÙØ§Ù Ø²ÙØªØ§Ù ÙØºØ§Ø²Ø§Ù ÙÙÙØµÙÙÙ Ø¹ÙØ¯ Ø§ÙØ³Ø·Ø­. Ø§ÙØ®Ø·ÙØ© Ø§ÙØµØ­ÙØ­Ø© ÙÙ Recombination Ø«Ù Ø¥Ø¬Ø±Ø§Ø¡ Ø§Ø®ØªØ¨Ø§Ø±Ø§Øª PVT Ø§ÙÙÙØ§Ø³Ø¨Ø©. Ø¥Ø°Ø§ Ø£Ø¸ÙØ±Øª Ø§ÙØ¨ÙØ§ÙØ§Øª Ø£Ù Ø§ÙØ³Ø§Ø¦Ù Black Oil ÙÙÙÙ ØªØ¬ÙÙØ² PVTO. Ø£ÙØ§ Ø¥Ø°Ø§ ÙØ§Ù Volatile Oil Ø£Ù Gas Condensate Ø£Ù ØºÙÙ Ø¨Ø§ÙÙØ±ÙØ¨Ø§Øª Ø§ÙØ®ÙÙÙØ©Ø ÙØ§ÙØ£ÙØ¶Ù Ø§Ø³ØªØ®Ø¯Ø§Ù EOS Ù Compositional Simulation.
'''

def ask_ai(user_text, file_context=None):
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': GLOBAL_PVT_REFERENCE}
    ]
    if file_context:
        messages.append({'role': 'user', 'content': 'Extra uploaded PVT report context for this chat only:\n\n' + file_context[:25000]})
    messages.append({'role': 'user', 'content': user_text})
    headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': TEXT_MODEL, 'messages': messages, 'temperature': 0.10, 'max_tokens': 3500}
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        data = response.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        return str(data)[:1500]
    except Exception as e:
        return 'ØµØ§Ø± Ø®Ø·Ø£ ÙÙ Ø§ÙØ§ØªØµØ§Ù Ø¨Ø§ÙØ°ÙØ§Ø¡ Ø§ÙØ§ØµØ·ÙØ§Ø¹Ù:\n' + str(e)

def encode_image_to_data_url(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = 'image/jpeg'
    with open(file_path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    return f'data:{mime_type};base64,{b64}'

def ask_vision_ai(prompt, image_path, file_context=None):
    image_data_url = encode_image_to_data_url(image_path)
    full_prompt = SYSTEM_PROMPT + '\n\n' + GLOBAL_PVT_REFERENCE + '\n\nGraph Interpretation Task:\n' + prompt
    if file_context:
        full_prompt += '\n\nExtra report context:\n' + file_context[:12000]
    messages = [{'role': 'user', 'content': [{'type': 'text', 'text': full_prompt}, {'type': 'image_url', 'image_url': {'url': image_data_url}}]}]
    headers = {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}
    payload = {'model': VISION_MODEL, 'messages': messages, 'temperature': 0.10, 'max_tokens': 2500}
    try:
        response = requests.post(GROQ_URL, headers=headers, json=payload, timeout=90)
        data = response.json()
        if 'choices' in data:
            return data['choices'][0]['message']['content']
        return str(data)[:1500]
    except Exception as e:
        return 'ØµØ§Ø± Ø®Ø·Ø£ ÙÙ ØªØ­ÙÙÙ Ø§ÙØµÙØ±Ø©:\n' + str(e)

def extract_pdf_text(file_path):
    text = ''
    reader = PdfReader(file_path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + '\n\n'
    return text.strip()

def extract_docx_text(file_path):
    doc = Document(file_path)
    text = ''
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text += paragraph.text + '\n'
    return text.strip()

def download_telegram_file(file_id, file_name):
    file_info = requests.get(f'{TELEGRAM_URL}/getFile', params={'file_id': file_id}, timeout=30).json()
    file_path = file_info['result']['file_path']
    file_url = f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
    suffix = os.path.splitext(file_name)[1] or '.bin'
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()
    file_data = requests.get(file_url, timeout=60).content
    with open(temp.name, 'wb') as f:
        f.write(file_data)
    return temp.name

def handle_document(chat_id, document):
    file_id = document['file_id']
    file_name = document.get('file_name', 'uploaded_file')
    mime_type = document.get('mime_type', '')
    try:
        local_path = download_telegram_file(file_id, file_name)
        lower_name = file_name.lower()
        if lower_name.endswith('.pdf'):
            extracted_text = extract_pdf_text(local_path)
            if not extracted_text:
                send_message(chat_id, 'ÙØ±Ø£Øª ÙÙÙ PDF ÙÙÙ ÙØ§ ÙØ¯Ø±ØªØ´ ÙØ³ØªØ®Ø±Ø¬ ÙØµ ÙØ§Ø¶Ø­. ÙÙÙÙ ÙÙÙÙ Ø§ÙÙÙÙ Ø³ÙØ§Ù ØµÙØ±Ø©. Ø§Ø±Ø³ÙÙ ØµÙØ±Ø© Ø§ÙØ±Ø³Ù Ø£Ù Ø§ÙØªÙØ±ÙØ± ÙØµÙØ±Ø© ÙÙØªØ­ÙÙÙ Ø§ÙØ¨ØµØ±Ù.')
                return
            FILE_CONTEXT[chat_id] = extracted_text
            send_message(chat_id, 'ØªÙ ÙØ±Ø§Ø¡Ø© PDF Ø¨ÙØ¬Ø§Ø­.\n\nØ§ÙÙÙÙ ØµØ§Ø± ÙØ±Ø¬Ø¹ Ø¥Ø¶Ø§ÙÙ ÙÙØ°Ù Ø§ÙÙØ­Ø§Ø¯Ø«Ø©.\n\nØ¬Ø±Ø¨Ù:\n/analyze\nØ­ÙÙ Ø§ÙØªÙØ±ÙØ± ÙØ­Ø¯Ø¯ ÙÙØ¹ Ø§ÙØ¹ÙÙØ© ÙØ§ÙØ§Ø®ØªØ¨Ø§Ø±Ø§Øª ÙØ§ÙØ­Ø³Ø§Ø¨Ø§Øª ÙØ§ÙØ±Ø³ÙÙØ§Øª Ø§ÙÙØ·ÙÙØ¨Ø©.')
            return
        if lower_name.endswith('.docx'):
            extracted_text = extract_docx_text(local_path)
            if not extracted_text:
                send_message(chat_id, 'ÙØ±Ø£Øª ÙÙÙ DOCX ÙÙÙ ÙØ§ ÙÙÙØªØ´ ÙØµ ÙØ§Ø¶Ø­.')
                return
            FILE_CONTEXT[chat_id] = extracted_text
            send_message(chat_id, 'ØªÙ ÙØ±Ø§Ø¡Ø© DOCX Ø¨ÙØ¬Ø§Ø­.\n\nØ§ÙÙÙÙ ØµØ§Ø± ÙØ±Ø¬Ø¹ Ø¥Ø¶Ø§ÙÙ ÙÙØ°Ù Ø§ÙÙØ­Ø§Ø¯Ø«Ø©.')
            return
        if mime_type.startswith('image/') or lower_name.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            IMAGE_CONTEXT[chat_id] = local_path
            send_message(chat_id, 'ØªÙ Ø§Ø³ØªÙØ§Ù Ø§ÙØµÙØ±Ø© Ø¨ÙØ¬Ø§Ø­.\n\nØ§ÙØªØ¨:\n/graph\nØ­ÙÙ Ø§ÙØ±Ø³Ù ÙÙØ¯Ø³ÙØ§Ù')
            return
        send_message(chat_id, 'Ø§ÙÙÙÙ ÙØ§Ø²Ù ÙÙÙÙ PDF Ø£Ù DOCX Ø£Ù ØµÙØ±Ø©.')
    except Exception as e:
        send_message(chat_id, 'ØµØ§Ø± Ø®Ø·Ø£ Ø£Ø«ÙØ§Ø¡ ÙØ±Ø§Ø¡Ø© Ø§ÙÙÙÙ:\n' + str(e))

def handle_photo(chat_id, photos):
    try:
        best_photo = photos[-1]
        file_id = best_photo['file_id']
        local_path = download_telegram_file(file_id, 'uploaded_graph.jpg')
        IMAGE_CONTEXT[chat_id] = local_path
        send_message(chat_id, 'ØªÙ Ø§Ø³ØªÙØ§Ù Ø§ÙØµÙØ±Ø© Ø¨ÙØ¬Ø§Ø­.\n\nØ§ÙØªØ¨:\n/graph\nØ­ÙÙ Ø§ÙØ±Ø³Ù ÙÙØ¯Ø³ÙØ§Ù ÙØ­Ø¯Ø¯ Ø§ÙØ³ÙÙÙ ÙØ§ÙÙÙØ§Ø­Ø¸Ø§Øª')
    except Exception as e:
        send_message(chat_id, 'ØµØ§Ø± Ø®Ø·Ø£ Ø£Ø«ÙØ§Ø¡ ØªØ­ÙÙÙ Ø§ÙØµÙØ±Ø©:\n' + str(e))

def parse_numbers_list(text, key):
    pattern = key + r'\s*=\s*\[([^\]]+)\]'
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    numbers = []
    for item in match.group(1).split(','):
        try:
            numbers.append(float(item.strip()))
        except Exception:
            pass
    return numbers

def try_generate_plot(chat_id, text):
    pressure = parse_numbers_list(text, 'Pressure')
    props = [('Bo', 'Oil Formation Volume Factor'), ('Rs', 'Solution Gas-Oil Ratio'), ('Density', 'Fluid Density'), ('Viscosity', 'Oil Viscosity'), ('RelativeVolume', 'Relative Volume'), ('YFunction', 'Y-Function'), ('Z', 'Gas Deviation Factor'), ('Bg', 'Gas Formation Volume Factor'), ('LiquidDropout', 'Liquid Dropout'), ('CGR', 'Condensate-Gas Ratio')]
    if not pressure:
        return False
    selected_label, selected_values = None, None
    for key, label in props:
        values = parse_numbers_list(text, key)
        if values and len(values) == len(pressure):
            selected_label, selected_values = label, values
            break
    if not selected_values:
        return False
    fig, ax = plt.subplots()
    ax.plot(pressure, selected_values, marker='o')
    ax.set_xlabel('Pressure')
    ax.set_ylabel(selected_label)
    ax.set_title('Pressure vs ' + selected_label)
    ax.grid(True)
    image_path = tempfile.NamedTemporaryFile(delete=False, suffix='.png').name
    plt.savefig(image_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    send_photo(chat_id, image_path, 'Graph generated: Pressure vs ' + selected_label)
    IMAGE_CONTEXT[chat_id] = image_path
    return True

def is_graph_command(text):
    t = text.lower().strip()
    return t.startswith('/graph') or t.startswith('/interpret_graph') or t.startswith('/interpret graph')

def is_plot_command(text):
    return text.lower().strip().startswith('/plot')

def is_export_command(text):
    t = text.lower().strip()
    return t.startswith('/export_sim') or t.startswith('/pvto') or t.startswith('/pvtg') or t.startswith('/eclipse') or t.startswith('/cmg')

def is_surface_separator_question(text):
    t = text.lower()
    has_oil = ('surface separator oil' in t or 'separator oil' in t or 'Ø¹ÙÙØ© Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ' in t or 'Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ' in t or 'Ø²ÙØª ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù' in t)
    has_gas = ('separator gas' in t or 'Ø¹ÙÙØ© ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ' in t or 'ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ' in t or 'ØºØ§Ø² ÙÙ Ø§ÙÙØ§ØµÙ Ø§ÙØ³Ø·Ø­Ù' in t)
    return has_oil and has_gas

while True:
    try:
        updates = requests.get(f'{TELEGRAM_URL}/getUpdates', params={'offset': offset + 1, 'timeout': 30}, timeout=40).json()
        for update in updates.get('result', []):
            offset = update['update_id']
            if 'message' not in update:
                continue
            message = update['message']
            chat_id = message['chat']['id']
            if 'document' in message:
                handle_document(chat_id, message['document'])
                continue
            if 'photo' in message:
                handle_photo(chat_id, message['photo'])
                continue
            if 'text' not in message:
                continue
            text = message['text']
            context = FILE_CONTEXT.get(chat_id)
            if text == '/start':
                reply = 'Ø£ÙÙØ§Ù Ø¨Ù ÙÙ PVT Lab AI Bot.\n\nØ£ÙØ§ ÙØ³Ø§Ø¹Ø¯ ÙÙØ¯Ø³Ù ÙØªØ®ØµØµ ÙÙ PVT Lab Ù Reservoir Fluid Analysis Ù Reservoir Simulation.\n\nØ§ÙØ£ÙØ§ÙØ±:\n/analyze\n/report\n/calc\n/plot\n/graph\n/interpret_graph\n/check\n/export_sim\n/pvto\n/pvtg\n/eclipse\n/cmg'
                send_message(chat_id, reply)
                continue
            if is_surface_separator_question(text):
                send_message(chat_id, surface_separator_analysis_ar())
                continue
            if is_graph_command(text):
                image_path = IMAGE_CONTEXT.get(chat_id)
                if not image_path:
                    send_message(chat_id, 'Ø§Ø±Ø³ÙÙ ØµÙØ±Ø© Ø§ÙØ±Ø³Ù Ø£Ù Figure Ø£ÙÙØ§ÙØ ÙØ¨Ø¹Ø¯ÙØ§ Ø§ÙØªØ¨Ù /graph.')
                    continue
                prompt = text + '\n\nAnalyze this engineering graph professionally. Identify graph type, axes, trend, anomalies, non-physical behavior, retrograde behavior if applicable, contamination indicators, separator performance issues, engineering meaning, possible causes, and recommendations.'
                reply = ask_vision_ai(prompt, image_path, context)
                send_message(chat_id, reply)
                continue
            if is_plot_command(text):
                try_generate_plot(chat_id, text)
                reply = ask_ai(text, context)
                send_message(chat_id, reply)
                continue
            if is_export_command(text):
                export_prompt = text + '\n\nGenerate simulator export guidance or formatting. Adapt to fluid type and data availability. Include unit validation, consistency checks, simulator warnings, black-oil vs compositional decision, Eclipse/CMG keyword guidance, and missing required data if needed.'
                reply = ask_ai(export_prompt, context)
                send_message(chat_id, reply)
                continue
            reply = ask_ai(text, context)
            send_message(chat_id, reply)
    except Exception as e:
        print(e)
    time.sleep(1)
