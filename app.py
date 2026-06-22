"""
Time to Hire — Keboola Data App PoC
====================================
A minimal Flask app that renders the Time to Hire tab live from Keboola Storage
and (optionally) embeds Kai chat so stakeholders can ask their own questions.

Data source:  out.c-TTH---tth-jobs.tth_jobs  (2,231 rows, refreshed 4x/day by Flow A)
Read path:    Keboola Input Mapping drops the table as a CSV at
              /data/in/tables/tth_jobs.csv before the app starts. No token needed
              for the data itself. (Local dev falls back to sample_tth_jobs.csv.)
Kai chat:     see kai_chat.py — needs a MASTER token in env STORAGE_API_TOKEN.
              The app runs fine without it; the chat box just reports "not configured".

Health check: Keboola GETs and POSTs "/" to confirm the app is up. Both return 200.
Port:         5000 (Flask default for Keboola Python apps).
"""

import csv
import io
import os
import statistics
from flask import Flask, request, render_template_string

import kai_chat

app = Flask(__name__)

# Keboola input mapping writes here; sample file is the local-dev fallback.
INPUT_CSV = "/data/in/tables/tth_jobs.csv"
SAMPLE_CSV = os.path.join(os.path.dirname(__file__), "sample_tth_jobs.csv")

# Year flag columns in the table: a job counts toward a year if has_t2f_<year> == 1.
YEARS = ["2026", "2025", "2024", "2023"]


def load_rows():
    """Return list[dict] of tth_jobs. Prefers Keboola input mapping, falls back to sample."""
    path = INPUT_CSV if os.path.exists(INPUT_CSV) else SAMPLE_CSV
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f)), os.path.basename(path)


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute(rows, year):
    """Filter to filled jobs (has_t2f==1) for the chosen year and compute KPIs + table."""
    flag = "has_t2f" if year == "all" else f"has_t2f_{year}"
    filled = [r for r in rows if r.get(flag) in ("1", "1.0")]

    def avg(col):
        vals = [to_num(r.get(col)) for r in filled]
        vals = [v for v in vals if v is not None]
        return round(statistics.mean(vals), 1) if vals else None

    kpis = {
        "hires": len(filled),
        "avg_tth": avg("tth"),
        "avg_t2find": avg("t2find"),
        "avg_t2fill": avg("t2fill"),
    }
    table = sorted(filled, key=lambda r: r.get("date_first_hired") or "", reverse=True)
    return kpis, table


PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<title>Time to Hire — Tribe</title>
<style>
 body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1117;color:#e6e8ee;margin:0;padding:24px}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#8b90a0;font-size:13px;margin-bottom:20px}
 .kpis{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
 .card{background:#1a1d29;border:1px solid #262b3a;border-radius:10px;padding:16px 20px;min-width:150px}
 .card .v{font-size:28px;font-weight:600} .card .l{color:#8b90a0;font-size:12px;margin-top:4px}
 .bar{display:flex;gap:12px;align-items:center;margin-bottom:16px}
 select{background:#1a1d29;color:#e6e8ee;border:1px solid #262b3a;border-radius:6px;padding:6px 10px}
 table{width:100%;border-collapse:collapse;font-size:13px} th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #1f2433}
 th{color:#8b90a0;font-weight:500} tr:hover td{background:#161925}
 .num{text-align:right;font-variant-numeric:tabular-nums}
 .kai{margin-top:28px;background:#1a1d29;border:1px solid #262b3a;border-radius:10px;padding:16px}
 .kai textarea{width:100%;background:#0f1117;color:#e6e8ee;border:1px solid #262b3a;border-radius:6px;padding:8px;box-sizing:border-box}
 .kai button{margin-top:8px;background:#3b6cf6;color:#fff;border:0;border-radius:6px;padding:8px 16px;cursor:pointer}
 .ans{margin-top:12px;white-space:pre-wrap;color:#c6cad6;font-size:13px}
 .warn{color:#e0a458;font-size:12px}
</style></head><body>
 <h1>Time to Hire</h1>
 <div class="sub">Live from Keboola Storage · source <code>out.c-TTH---tth-jobs.tth_jobs</code> · loaded from {{ src }} · {{ total }} jobs</div>

 <form class="bar" method="get">
   <label for="year">Year</label>
   <select id="year" name="year" onchange="this.form.submit()">
     <option value="all" {{ 'selected' if year=='all' }}>All</option>
     {% for y in years %}<option value="{{y}}" {{ 'selected' if year==y }}>{{y}}</option>{% endfor %}
   </select>
 </form>

 <div class="kpis">
   <div class="card"><div class="v">{{ kpis.hires }}</div><div class="l">Filled roles</div></div>
   <div class="card"><div class="v">{{ kpis.avg_tth if kpis.avg_tth is not none else '—' }}</div><div class="l">Avg time to hire (days)</div></div>
   <div class="card"><div class="v">{{ kpis.avg_t2find if kpis.avg_t2find is not none else '—' }}</div><div class="l">Avg time to find (days)</div></div>
   <div class="card"><div class="v">{{ kpis.avg_t2fill if kpis.avg_t2fill is not none else '—' }}</div><div class="l">Avg time to fill (days)</div></div>
 </div>

 <table>
  <tr><th>Client</th><th>Role</th><th>Category</th><th>TA</th><th>Hired</th>
      <th class="num">TTH</th><th class="num">T2Find</th><th class="num">T2Fill</th></tr>
  {% for r in table[:200] %}
   <tr><td>{{ r.client_name }}</td><td>{{ r.job_title }}</td><td>{{ r.job_category }}</td><td>{{ r.ta }}</td>
       <td>{{ r.date_first_hired }}</td>
       <td class="num">{{ r.tth }}</td><td class="num">{{ r.t2find }}</td><td class="num">{{ r.t2fill }}</td></tr>
  {% endfor %}
 </table>
 {% if table|length > 200 %}<div class="sub">Showing first 200 of {{ table|length }}.</div>{% endif %}

 <div class="kai">
   <strong>Ask Kai about this data</strong>
   {% if not kai_ready %}<div class="warn">Kai not configured — set the STORAGE_API_TOKEN (master token) secret to enable.</div>{% endif %}
   <form method="post" action="/chat">
     <textarea name="q" rows="2" placeholder="e.g. average time to hire for tech roles in 2026 vs non-tech">{{ q or '' }}</textarea><br>
     <button type="submit" {{ 'disabled' if not kai_ready }}>Ask</button>
   </form>
   {% if answer %}<div class="ans">{{ answer }}</div>{% endif %}
 </div>
</body></html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    rows, src = load_rows()
    year = request.args.get("year", "2026")
    kpis, table = compute(rows, year)
    return render_template_string(
        PAGE, kpis=kpis, table=table, year=year, years=YEARS,
        total=len(rows), src=src, kai_ready=kai_chat.is_configured(),
        q=None, answer=None,
    )


@app.route("/chat", methods=["POST"])
def chat():
    rows, src = load_rows()
    year = request.args.get("year", "2026")
    kpis, table = compute(rows, year)
    q = request.form.get("q", "").strip()
    answer = kai_chat.ask(q) if q else None
    return render_template_string(
        PAGE, kpis=kpis, table=table, year=year, years=YEARS,
        total=len(rows), src=src, kai_ready=kai_chat.is_configured(),
        q=q, answer=answer,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
