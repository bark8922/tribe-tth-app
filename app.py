"""
Time to Hire - Keboola Data App PoC.

Renders the Time to Hire tab live from Keboola Storage and embeds Kai chat.
Kai's agent loop can take 20-40s, longer than the Keboola apps proxy will hold a
single HTTP request open (it returns 502). So /chat starts the Kai call in a
background thread and the page polls /chat_status until the answer is ready.
"""

import csv
import os
import statistics
import threading
import uuid

from flask import Flask, request, jsonify, render_template_string

import kai_chat

app = Flask(__name__)

INPUT_CSV = "/data/in/tables/tth_jobs.csv"
SAMPLE_CSV = os.path.join(os.path.dirname(__file__), "sample_tth_jobs.csv")
YEARS = ["2026", "2025", "2024", "2023"]

JOBS = {}  # job_id -> {"status": "pending"|"done", "answer": str}


def load_rows():
    path = INPUT_CSV if os.path.exists(INPUT_CSV) else SAMPLE_CSV
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f)), os.path.basename(path)


def to_num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def compute(rows, year):
    flag = "has_t2f" if year == "all" else "has_t2f_%s" % year
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


def _run_kai(job_id, q):
    try:
        ans = kai_chat.ask(q)
    except Exception as e:
        ans = "Kai error: %s" % e
    JOBS[job_id] = {"status": "done", "answer": ans}


PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<title>Time to Hire - Tribe</title>
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
 .qline{margin-top:10px;color:#8b90a0;font-size:12px}
 .ans{margin-top:10px;white-space:pre-wrap;color:#c6cad6;font-size:13px;line-height:1.5}
 .warn{color:#e0a458;font-size:12px}
</style></head><body>
 <h1>Time to Hire</h1>
 <div class="sub">Live from Keboola Storage - source <code>out.c-TTH---tth-jobs.tth_jobs</code> - loaded from {{ src }} - {{ total }} jobs</div>

 <form class="bar" method="get">
   <label for="year">Year</label>
   <select id="year" name="year" onchange="this.form.submit()">
     <option value="all" {{ 'selected' if year=='all' }}>All</option>
     {% for y in years %}<option value="{{y}}" {{ 'selected' if year==y }}>{{y}}</option>{% endfor %}
   </select>
 </form>

 <div class="kpis">
   <div class="card"><div class="v">{{ kpis.hires }}</div><div class="l">Filled roles</div></div>
   <div class="card"><div class="v">{{ kpis.avg_tth if kpis.avg_tth is not none else '-' }}</div><div class="l">Avg time to hire (days)</div></div>
   <div class="card"><div class="v">{{ kpis.avg_t2find if kpis.avg_t2find is not none else '-' }}</div><div class="l">Avg time to find (days)</div></div>
   <div class="card"><div class="v">{{ kpis.avg_t2fill if kpis.avg_t2fill is not none else '-' }}</div><div class="l">Avg time to fill (days)</div></div>
 </div>

 <table>
  <tr><th>Client</th><th>Role</th><th>Category</th><th>TA</th><th>Hired</th>
      <th class="num">TTH</th><th class="num">T2Find</th><th class="num">T2Fill</th></tr>
  {% for r in table[:50] %}
   <tr><td>{{ r.client_name }}</td><td>{{ r.job_title }}</td><td>{{ r.job_category }}</td><td>{{ r.ta }}</td>
       <td>{{ r.date_first_hired }}</td>
       <td class="num">{{ r.tth }}</td><td class="num">{{ r.t2find }}</td><td class="num">{{ r.t2fill }}</td></tr>
  {% endfor %}
 </table>
 {% if table|length > 50 %}<div class="sub">Showing first 50 of {{ table|length }}.</div>{% endif %}

 <div class="kai" id="kai">
   <strong>Ask Kai about this data</strong>
   {% if not kai_ready %}<div class="warn">Kai not configured - set the STORAGE_API_TOKEN (master token) secret to enable.</div>{% endif %}
   <form method="post" action="/chat#kai">
     <textarea name="q" rows="2" placeholder="e.g. average time to hire for sales roles">{{ q or '' }}</textarea><br>
     <button type="submit" {{ 'disabled' if not kai_ready }}>Ask</button>
   </form>
   {% if q %}<div class="qline">You asked: {{ q }}</div>{% endif %}
   <div class="ans" id="ans"></div>
 </div>

 {% if job_id %}
 <script>
 var JOB = "{{ job_id }}";
 var el = document.getElementById("ans");
 el.textContent = "Kai is thinking... (this can take 20-40s)";
 function poll(){
   fetch("/chat_status?job=" + JOB).then(function(r){ return r.json(); }).then(function(d){
     if (d.status === "done"){ el.textContent = d.answer || "(no answer)"; }
     else { setTimeout(poll, 2000); }
   }).catch(function(){ setTimeout(poll, 3000); });
 }
 poll();
 if (location.hash !== "#kai"){ location.hash = "#kai"; }
 </script>
 {% endif %}
</body></html>
"""


def render(q=None, job_id=None):
    rows, src = load_rows()
    year = request.args.get("year", "2026")
    kpis, table = compute(rows, year)
    return render_template_string(
        PAGE, kpis=kpis, table=table, year=year, years=YEARS,
        total=len(rows), src=src, kai_ready=kai_chat.is_configured(),
        q=q, job_id=job_id,
    )


@app.route("/", methods=["GET", "POST"])
def index():
    return render()


@app.route("/chat", methods=["POST"])
def chat():
    q = request.form.get("q", "").strip()
    job_id = None
    if q and kai_chat.is_configured():
        job_id = uuid.uuid4().hex
        JOBS[job_id] = {"status": "pending", "answer": None}
        threading.Thread(target=_run_kai, args=(job_id, q), daemon=True).start()
    return render(q=q, job_id=job_id)


@app.route("/chat_status")
def chat_status():
    job = JOBS.get(request.args.get("job", ""))
    return jsonify(job or {"status": "unknown"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
