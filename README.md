# Time to Hire — Keboola Data App (PoC)

Proof-of-concept for moving a single dashboard tab off the static Cloudflare bundle and
onto a Keboola data app that reads Snowflake **live** and embeds **Kai** so stakeholders
can ask their own questions. Built to show Martin something concrete with the lowest
possible blast radius: it reads one existing table and touches nothing in the live pipeline.

## What it does

- Reads `out.c-TTH---tth-jobs.tth_jobs` (2,231 rows, refreshed 4x/day by Flow A).
- Shows KPI cards (avg time to hire / find / fill, filled-role count) + a per-job table.
- Year filter (All / 2026 / 2025 / 2024 / 2023) using the table's `has_t2f_<year>` flags.
- A "Ask Kai" box that answers questions about the data in plain English (when configured).

## Architecture

```
Flow A (4x/day) ──> out.c-TTH---tth-jobs.tth_jobs ──[input mapping]──> /data/in/tables/tth_jobs.csv
                                                                              │
                                                              Flask app (app.py) renders page
                                                                              │
                                                       "Ask Kai" ──> kai_chat.py ──> Kai (master token)
```

The **data** comes through Keboola Input Mapping (a CSV, no token needed). The **only**
thing that needs a token is Kai chat, and it needs a **master** token, isolated in
`kai_chat.py`.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask app: data load, KPIs, table, page. Listens on port 5000, answers GET+POST on `/`. |
| `kai_chat.py` | Kai integration. The only place the master token is used. Degrades gracefully if absent. |
| `requirements.txt` | `flask` (+ optional `kai-client`). |
| `setup.sh` | Keboola runs this on deploy to install deps. |
| `sample_tth_jobs.csv` | Local-dev fallback data so it runs without Keboola. |

## Run locally (no Keboola needed)

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000  (uses sample_tth_jobs.csv)
```

## Deploy in Keboola (when you're ready — not done yet)

1. Push this folder to a GitHub repo (or a branch of `bark8922/tribe-recruiting`).
2. In Keboola → Data Apps → create a Python/JS app pointing at the repo + branch.
3. **Input mapping:** map `out.c-TTH---tth-jobs.tth_jobs` so it lands at
   `/data/in/tables/tth_jobs.csv`.
4. **Access:** restrict to the stakeholders who should see it.
5. **Sleep:** leave auto-sleep on (5 min–24 hr) so you only pay while it's in use.
6. **Kai (optional):** add secret env vars
   - `STORAGE_API_TOKEN` = a **master** token (see security note below)
   - `STORAGE_API_URL` = `https://connection.eu-central-1.keboola.com`

## Security note on the Kai master token

Kai requires a master token = full admin access to project 855. If that secret leaks it is
full-project compromise, and it can only be revoked by removing the user from the project.
**Recommendation:** create a dedicated service admin user (e.g. `kai-app@tribe.xyz`) and use
its master token here, never a personal one. Then you can revoke by deleting that user. Never
log the value.

## Cost

~$230/mo in credits for an always-on app, but with auto-sleep you only pay while someone is
using it, regardless of viewer count. Kai questions are billed in Keboola credits per query.
Funded comfortably by the ~4,000 banked credits from the current contract.

## Status

Skeleton only. Not deployed. No tokens created. Renders correctly against the sample data;
swap to live data via the input mapping step above.
