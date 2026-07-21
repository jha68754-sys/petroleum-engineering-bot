"""
Glossary service module.

Generates an interactive HTML glossary with:
- Searchable Arabic/English terms
- PVT relationship reference cards
- ASCII sketch previews
- Responsive dark/light theme
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from constants import KNOWLEDGE_BASE, PVT_PLOT_RULES, ASCII_SKETCHES

logger = logging.getLogger("pvt_bot.services.glossary")


# Cache for the generated HTML
_glossary_cache: Dict[str, bytes] = {}


def generate_glossary_html() -> bytes:
    """
    Generate the full interactive HTML glossary.

    The result is cached after first generation to avoid
    repeated expensive HTML/JS assembly.

    Returns:
        The complete HTML document as UTF-8 bytes.
    """
    if "html" in _glossary_cache:
        logger.info("Glossary HTML served from cache")
        return _glossary_cache["html"]

    # Build terms JSON array
    terms_data = []
    for entry in KNOWLEDGE_BASE:
        category = entry["category"]
        if "PVT" in category:
            cls = "b-pvt"
            lbl = "PVT"
        elif "Reservoir" in category:
            cls = "b-res"
            lbl = "Reservoir"
        elif "Drilling" in category:
            cls = "b-drl"
            lbl = "Drilling"
        elif "Production" in category:
            cls = "b-pro"
            lbl = "Production"
        elif "Economics" in category:
            cls = "b-eco"
            lbl = "Economics"
        else:
            cls = "b-res"
            lbl = "General"

        search_str = f"{entry['en'].lower()} {entry['ar']} {entry['def_ar']}".lower()
        extras = [
            entry["def_ar"],
            f"Trend: {entry['trend']}",
            f"Range: {entry['typical_range']}",
        ]
        if entry.get("relationship_key"):
            extras.append(f"Plot: {entry['relationship_key']}")

        terms_data.append({
            "ar": entry["ar"],
            "en": entry["en"],
            "def": entry["def_ar"],
            "cls": cls,
            "lbl": lbl,
            "extras": extras,
            "search": search_str,
        })

    # Build plots JSON array
    plots_data = []
    for key, rule in PVT_PLOT_RULES.items():
        sketch = ASCII_SKETCHES.get(key, "No sketch available")
        plots_data.append({
            "title_ar": rule["title_ar"],
            "title_en": rule["title_en"],
            "definition": rule["definition"],
            "x_axis": rule["x_axis"],
            "y_axis": rule["y_axis"],
            "shape": rule["shape"],
            "pivot": rule["pivot"],
            "mistakes": rule.get("common_ai_mistakes", []),
            "rows": [
                f"Above Sat: {rule.get('above_saturation', 'n/a')}",
                f"At Sat: {rule.get('at_saturation', 'n/a')}",
                f"Below Sat: {rule.get('below_saturation', 'n/a')}",
            ],
            "sketch": sketch,
        })

    term_json = json.dumps(terms_data, ensure_ascii=False)
    plot_json = json.dumps(plots_data, ensure_ascii=False)

    css = r"""
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@400;600;700;900&family=Fira+Code:wght@400;600&display=swap');
:root{--crude:#1A0F08;--paper:#FAF6F0;--light:#F0EBE3;--amber:#C8760A;--border:#D5CDBF;--muted:#7A7060;--dbg:#0D1117}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Noto Sans Arabic','Segoe UI',sans-serif;background:var(--paper);color:var(--crude);min-height:100vh}
header{text-align:center;padding:2rem 1rem;background:var(--light);border-bottom:3px solid var(--amber)}
header h1{font-size:1.6rem;font-weight:900}
header h1 span{color:var(--amber)}
header p{font-size:.85rem;color:var(--muted);margin-top:.3rem}
nav{display:flex;gap:.5rem;padding:.8rem 1rem;justify-content:center;flex-wrap:wrap;
    background:var(--paper);border-bottom:2px solid var(--border);
    position:sticky;top:0;z-index:100;box-shadow:0 2px 10px rgba(0,0,0,.07)}
nav button{padding:.45rem 1.1rem;border:2px solid var(--border);border-radius:999px;
    background:transparent;font-family:inherit;font-size:.82rem;font-weight:600;
    color:var(--muted);cursor:pointer;transition:all .2s}
nav button:hover{border-color:var(--amber);color:var(--amber)}
nav button.active{background:var(--amber);border-color:var(--amber);color:#fff}
main{max-width:1100px;margin:0 auto;padding:2rem 1.5rem 4rem}
.sec{display:none}.sec.active{display:block}
.search input{width:100%;padding:.7rem 1.2rem;border:2px solid var(--border);
    border-radius:8px;font-family:inherit;font-size:1rem;background:var(--paper);
    margin-bottom:1.5rem}
.search input:focus{outline:none;border-color:var(--amber)}
.grid{display:grid;gap:1rem}
.card{background:var(--paper);border:1.5px solid var(--border);border-radius:10px;overflow:hidden}
.card:hover{box-shadow:0 4px 18px rgba(200,118,10,.14);border-color:var(--amber)}
.card-head{display:flex;align-items:center;gap:.8rem;padding:.9rem 1.3rem;
    cursor:pointer;flex-wrap:wrap}
.ar{font-size:1rem;font-weight:700;color:var(--crude);flex:1}
.en{font-family:'Fira Code',monospace;font-size:.82rem;font-weight:600;color:var(--amber);
    background:var(--light);padding:.2rem .6rem;border-radius:5px;direction:ltr}
.badge{font-size:.68rem;padding:.18rem .55rem;border-radius:999px;font-weight:700}
.b-res{background:#dbeafe;color:#1e40af}.b-pvt{background:#fef9c3;color:#854d0e}.b-pro{background:#dcfce7;color:#166534}
.b-drl{background:#ffe4e6;color:#9f1239}.b-eco{background:#e0f2fe;color:#0369a1}
.card-body{display:none;padding:0 1.3rem 1.2rem;border-top:1px solid var(--border)}
.card-body.open{display:block}
.def{margin-top:.9rem;font-size:.95rem;line-height:1.85}
.extra{margin-top:.35rem;font-size:.8rem;color:var(--muted)}
.ftitle{font-size:1.3rem;font-weight:900;color:var(--crude);margin-bottom:1.2rem;
    border-bottom:3px solid var(--amber);padding-bottom:.4rem}
.pcard{background:var(--dbg);border-radius:10px;overflow:hidden;margin-bottom:1.2rem;border:1px solid #2a3040}
.pcard-head{display:flex;justify-content:space-between;padding:.8rem 1.3rem;
    background:rgba(200,118,10,.11);border-bottom:1px solid #2a3040;flex-wrap:wrap;gap:.4rem}
.p-en{font-family:'Fira Code',monospace;color:#e8a020;font-size:.85rem}
.p-ar{color:rgba(255,255,255,.85);font-weight:600}
.pcard-body{padding:1.1rem 1.3rem;color:rgba(255,255,255,.75);font-size:.85rem}
.p-def{font-style:italic;color:#e8a020;margin-bottom:.5rem}
.axes{font-family:'Fira Code',monospace;font-size:.78rem;margin-bottom:.5rem;color:rgba(255,255,255,.6)}
.shape{margin-bottom:.6rem;font-weight:600;color:rgba(255,255,255,.9)}
.prow{margin:.3rem 0}
.pivot{margin:.5rem 0;color:#e8a020;font-weight:600}
.ml{margin-top:.6rem;font-size:.78rem;color:rgba(255,100,100,.8);font-weight:700}
.mi{font-size:.75rem;color:rgba(255,120,120,.7);margin:.2rem 0}
.sketch{font-family:'Fira Code',monospace;font-size:.68rem;color:#9be9a8;background:#000;
    padding:.8rem;border-radius:6px;overflow-x:auto;direction:ltr;text-align:left;
    line-height:1.3;margin-top:.8rem}
.nr{text-align:center;padding:3rem;color:var(--muted)}
"""

    js = r"""
function renderTerms(list){
  document.getElementById("tgrid").innerHTML=list.map(function(t,i){
    var ex=(t.extras||[]).map(function(e){return '<div class="extra">'+e+'</div>';}).join("");
    return '<div class="card"><div class="card-head" onclick="tog('+i+')">'
      +'<span class="ar">'+t.ar+'</span>'
      +'<span class="en">'+t.en+'</span>'
      +'<span class="badge '+t.cls+'">'+t.lbl+'</span>'
      +'</div><div class="card-body" id="b'+i+'">'
      +'<p class="def">'+t.def+'</p>'+ex+'</div></div>';
  }).join("");
}
function tog(i){document.getElementById("b"+i).classList.toggle("open");}
function filterTerms(){
  var q=document.getElementById("q").value.toLowerCase();
  var f=q?TERMS.filter(function(t){return t.search.indexOf(q)!==-1;}):TERMS;
  renderTerms(f);
  document.getElementById("nr").style.display=f.length?"none":"block";
}
function renderPlots(){
  document.getElementById("pgrid").innerHTML=PLOTS.map(function(p){
    var rows=(p.rows||[]).map(function(r){return '<div class="prow">'+r+'</div>';}).join("");
    var mis=(p.mistakes||[]).map(function(m){return '<div class="mi">- '+m+'</div>';}).join("");
    return '<div class="pcard"><div class="pcard-head">'
      +'<span class="p-ar">'+p.title_ar+'</span>'
      +'<span class="p-en">'+p.title_en+'</span>'
      +'</div><div class="pcard-body">'
      +'<div class="p-def">'+p.definition+'</div>'
      +'<div class="axes">X: '+p.x_axis+' | Y: '+p.y_axis+'</div>'
      +'<div class="shape">'+p.shape+'</div>'
      +rows
      +'<div class="pivot">Pivot: '+p.pivot+'</div>'
      +(mis?'<div class="ml">REJECT (common mistakes):</div>'+mis:'')
      +'<pre class="sketch">'+p.sketch+'</pre>'
      +'</div></div>';
  }).join("");
}
function show(id,btn){
  document.querySelectorAll(".sec").forEach(function(s){s.classList.remove("active");});
  document.querySelectorAll("nav button").forEach(function(b){b.classList.remove("active");});
  document.getElementById(id).classList.add("active");
  btn.classList.add("active");
}
renderTerms(TERMS); renderPlots();
"""

    html = (
        '<!DOCTYPE html><html lang="ar" dir="rtl">'
        '<head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>Petroleum Engineering Glossary</title>'
        '<style>' + css + '</style></head><body>'
        '<header><h1>Petroleum Engineering <span>Glossary</span></h1>'
        '<p>PVT | Reservoir | Drilling | Production | Economics</p></header>'
        '<nav>'
        '<button class="active" onclick="show(\'terms\',this)">Terms / المصطلحات</button>'
        '<button onclick="show(\'plots\',this)">PVT Relationships / علاقات PVT</button>'
        '</nav><main>'
        '<div id="terms" class="sec active">'
        '<div class="search"><input id="q" placeholder="Search terms (AR/EN)..." oninput="filterTerms()"/></div>'
        '<div class="grid" id="tgrid"></div>'
        '<div class="nr" id="nr" style="display:none">No results found</div>'
        '</div>'
        '<div id="plots" class="sec">'
        '<p class="ftitle">PVT Properties vs Pressure -- Correct Physical Behavior (BLOCK 5)</p>'
        '<div id="pgrid"></div>'
        '</div>'
        '</main>'
        '<script>const TERMS=' + term_json + ';const PLOTS=' + plot_json + ';' + js + '</script>'
        '</body></html>'
    ).encode("utf-8")

    _glossary_cache["html"] = html
    logger.info("Glossary HTML generated and cached (%d bytes)", len(html))
    return html


def clear_glossary_cache() -> None:
    """Clear the glossary HTML cache."""
    _glossary_cache.clear()
