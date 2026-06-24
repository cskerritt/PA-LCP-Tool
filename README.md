# PA-LCP-Tool

A transparent, reproducible **Life Care Plan cost-projection engine** and
**court-ready Excel report generator**, built for admissibility under
*Daubert v. Merrell Dow Pharmaceuticals* and **Federal Rule of Evidence 702**.

Given a set of recommended care items and documented economic assumptions, the
tool produces a multi-tab Excel workbook that presents future medical-care costs
in three measures — **current (base-year) dollars**, **future (nominal) dollars**,
and **present value** — with every rate, source, percentile, and retrieval date
disclosed, and a built-in *Daubert pre-flight* that flags the defects courts most
often cite when excluding life care plans.

The repository contains two layers:

- **`palcp`** — the Python cost-projection **engine + CLI + Excel generator**
  (Phase 1). This is the Daubert-critical, reusable core and is UI-agnostic.
- **`palcp_web`** — a **FastAPI + HTMX multi-user web app** (Phase 2) that wraps
  the engine, backed by **PostgreSQL** and deployable to **Railway**. Manage
  cases, care items, pricing libraries, and rate libraries in the browser;
  generate and download the same Excel workbook. See
  [Web app](#web-app-phase-2) and [`docs/DEPLOY_RAILWAY.md`](docs/DEPLOY_RAILWAY.md).

---

## What it produces

A single `.xlsx` workbook with ten tabs, each able to stand alone as an exhibit:

| Tab | Contents |
| --- | --- |
| **Cover** | Caption, claimant, evaluator, dates, headline totals, disclaimer |
| **Summary** | Totals by category in all three measures + key assumptions |
| **Current-Cost Tables** | Itemized current-dollar LCP tables (no growth/discount) |
| **PV Projection** | Itemized lifetime nominal & present value, with net discount rates |
| **Annual Schedule** | Year-by-year nominal cost by category, discount factor, PV, cumulative PV |
| **Assumptions & Rates** | Every rate, its basis/source/date, and the exact formulas used |
| **Data Sources** | Provenance of each pricing source actually used + standard source notes |
| **Methodology & Standards** | IALCP standards, consensus statements, *Daubert* factors |
| **Medical Foundation** | Per-item basis in the treating record (flags any gaps) |
| **Validation** | The Daubert pre-flight findings (errors / warnings / notes) |

The **current-cost** tables and the **growth + present-value** projection are
presented as **separate, clearly-labeled tabs** in the same workbook.

---

## Install

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e .
```

Requires Python ≥ 3.10. Runtime dependencies: `openpyxl`, `PyYAML`.

## Quick start

```bash
# 1. See a complete, working example (synthetic data):
palcp sample --out sample.xlsx

# 2. Scaffold blank input templates to edit:
palcp init --dir lcp_inputs

# 3. Build from your own inputs:
palcp build \
  --assumptions lcp_inputs/assumptions.yaml \
  --items       lcp_inputs/plan_items.csv \
  --pricing     va_reasonable_charges.xlsx:va_reasonable_charges \
  --out         life_care_plan.xlsx

# 4. Run only the Daubert pre-flight (no workbook):
palcp validate --assumptions lcp_inputs/assumptions.yaml --items lcp_inputs/plan_items.csv
```

`--pricing` accepts one or more files, each optionally tagged with a loader
preset as `path:preset` (presets: `va_reasonable_charges`, `cms_dmepos`, `mfus`).
Items with a code but no `unit_cost` are priced from these tables; items with a
direct `unit_cost` (e.g. a vendor survey) keep it.

## Library use

```python
from palcp import (load_plan, load_pricing, apply_pricing,
                   validate_plan, project, save_workbook)

plan = load_plan("assumptions.yaml", "plan_items.csv")

# Optional: price any items that carry a code but no direct unit_cost.
apply_pricing(plan.items, load_pricing("pricing.csv"))

report = validate_plan(plan)        # Daubert pre-flight
result = project(plan)              # the cost projection
save_workbook(result, report, "life_care_plan.xlsx")
```

(Skip the `apply_pricing` line if every item already carries a `unit_cost`.)

---

## How the projection works (in one paragraph)

Each care item's current cost is grown to the year it is incurred using a
**published medical-price series** chosen for that item class (medical services,
prescription drugs, DME, facility, or wage-based attendant care), then
**discounted to present value** at a cited discount rate. Growth and discounting
use a single, consistent cash-flow **timing** convention (mid-year by default),
so the present value is exactly reproducible from the disclosed inputs. Life
expectancy sets the horizon; the final partial year is prorated. The full
formulas appear on the workbook's Assumptions tab and in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

## Defensibility

The tool is organized around the six life-care-plan peer-review domains and the
*Daubert* factors. The **Validation** tab/command checks for the specific
failures that recur in exclusion case law — missing medical foundation,
inconsistent ("cherry-picked") cost percentiles, un-sourced or undated pricing,
and speculative durations. (The generated workbook states these as general
principles; verify the controlling authority for your jurisdiction in the
expert's own report.) See
[`docs/DEFENSIBILITY.md`](docs/DEFENSIBILITY.md).

## Bringing your own pricing data

The tool does **not** ship proprietary fee schedules. It defines a single
canonical pricing schema and flexible loaders so your **VA Reasonable Charges**,
MFUS/Context4, CMS DMEPOS, Genworth, or vendor-survey exports map in cleanly.
See [`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md). The bundled sample uses
**synthetic, clearly-labeled** data only.

## Important limitations

- **Not legal or medical advice.** The tool quantifies costs from the inputs you
  provide; it does not establish medical necessity, causation, or life
  expectancy, which rest on the clinical record and qualified expert opinion.
- **Replace placeholder rates.** Built-in default growth/discount rates are
  tagged `PLACEHOLDER` and flagged by the validator until you substitute current,
  cited figures as of your report date.
- Figures are only as current as the cited retrieval dates.

## Web app (Phase 2)

`palcp_web` is a single FastAPI service (server-rendered with Jinja + HTMX) that
wraps the engine, with multi-user accounts and PostgreSQL persistence. Features:

- email/password accounts with per-user data isolation;
- a case dashboard; full assumptions editing (claimant, life expectancy, discount
  rate, growth series);
- care-item management (add/edit/delete inline, plus CSV/XLSX import);
- **pricing libraries** (upload VA Reasonable Charges / CMS DMEPOS / MFUS / vendor
  exports; link to a case to price items by code);
- **rate libraries** (save reusable growth-rate sets and apply them to a case);
- live Daubert validation and lifetime totals;
- one-click **Excel report generation**, stored and downloadable per case;
- an **edit history** (audit log) per case;
- a **default VA Reasonable Charges (UCR) pricing library**, auto-linked to every
  new case, with **type-a-code auto-fill** and a **common-items catalog** so you
  enter the minimum per item (see below).

### VA Reasonable Charges (default pricing) + minimal data entry

Every new case is automatically linked to a system-wide **VA Reasonable Charges**
library and prices line items by CPT/HCPCS code. To minimize data entry:

- set the claimant's **3-digit ZIP** on the case (the VA pricing locality);
- type a CPT/HCPCS code in the add-item form, or click **Add from common items** —
  the **price, description, code type, source, percentile, geographic basis,
  retrieval/effective date, category, and growth class** auto-fill from the VA
  library at the case's locality. You then set frequency/timing and the medical
  foundation. Unmatched codes are flagged, never guessed.

The tool ships a small, clearly-labeled **SAMPLE** seed so it runs out of the box.
To price from **real** VA charges, download the official VA outpatient/professional
workbook (after accepting the VA's AMA CPT-Code disclaimer — a click you are
entitled to make) and ingest it:

```bash
python scripts/fetch_va_charges.py \
  --outpatient ~/Downloads/va_outpatient.xlsx \
  --version v5.26 --effective 2026-01-01 \
  --out data/va_charges_normalized.csv
# restart the app: the default VA library reloads from the normalized CSV
```

The normalized CSV is **gitignored** — CPT® is AMA-copyrighted, and your CPT
license governs internal use. Only the labeled SAMPLE seed is committed. The VA
version, effective date, and locality are disclosed on the workbook's Data Sources
tab.

Run it locally:

```bash
python -m pip install -e ".[web,dev]"
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export SESSION_HTTPS_ONLY=0          # allow cookies over http://localhost
alembic upgrade head                 # defaults to a local SQLite db
uvicorn palcp_web.main:app --reload  # → http://127.0.0.1:8000
```

Deploy to Railway (Dockerfile + Postgres plugin): see
[`docs/DEPLOY_RAILWAY.md`](docs/DEPLOY_RAILWAY.md). The container runs
`alembic upgrade head` then `uvicorn` on `$PORT`; the Postgres `DATABASE_URL` is
picked up automatically and rewritten for the psycopg 3 driver.

## Development

```bash
python -m pip install -e ".[dev,web]"
python -m pytest
```

## Project layout

```
src/palcp/             # Phase 1 — engine
  models.py            #   dataclasses: Plan, CareItem, rates, life expectancy
  config.py            #   load assumptions (YAML) + items (CSV/XLSX) -> Plan
  validate.py          #   Daubert / FRE 702 pre-flight checks
  economics/           #   projection engine, timing, life table
  pricing/             #   canonical schema, vendor loaders, code resolution
  workbook/            #   openpyxl styles, multi-tab builder, narrative content
  cli.py               #   `palcp` command-line interface
  data/                #   templates + synthetic sample inputs
src/palcp_web/         # Phase 2 — FastAPI + HTMX web app
  models.py            #   SQLAlchemy models (users, cases, items, libraries…)
  routers/             #   auth, cases, items, pricing, rates, reports
  services.py          #   bridge: DB case -> palcp engine -> workbook
  templates/, static/  #   Jinja templates + CSS
  main.py, db.py, …    #   app, session/db, security, config
alembic/               # database migrations
Dockerfile, railway.json, scripts/start.sh   # Railway deployment
docs/                  # METHODOLOGY, DATA_SCHEMA, DEFENSIBILITY, DEPLOY_RAILWAY
tests/                 # pytest suite (engine + web)
```
