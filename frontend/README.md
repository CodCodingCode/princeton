# Frontend

Streamlit dashboards for the NeoVax pipeline. Both apps are thin UI layers — all logic lives in the `neoantigen` package under [../backend/](../backend/).

- [app.py](app.py) — plain pipeline dashboard (upload VCF/TSV → ranked candidates + mRNA construct + 3D view).
- [app_agent.py](app_agent.py) — agent-driven live dashboard (upload pathology PDF + tumor VCF → `CaseOrchestrator` runs the full flow with streaming events).

## What you need from the backend

### 1. The `neoantigen` package installed

The apps import directly from `neoantigen.*`. Install the backend editable, with the `[agent]` extra (which brings in `streamlit`, `plotly`, `py3Dmol`, `claude-agent-sdk`, `google-api-python-client`, etc.):

```bash
# from the repo root
pip install -e './backend[agent]'
# optional ML scoring (app.py's "mhcflurry" scorer option)
pip install -e './backend[agent,ml]' && mhcflurry-downloads fetch
```

Imports used by the apps:

| File           | Imports from `neoantigen`                                                                                                                    |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `app.py`       | `models`, `genes.GENE_TO_UNIPROT`, `pipeline.{parser,protein,peptides,scoring,filters,construct}`, `external.{dgidb,clinicaltrials}`         |
| `app_agent.py` | `agent.{AgentEvent, EventBus, EventKind, build_case_file, gmail_auth}`, `agent.emails.send_via_gmail`, `agent.orchestrator.CaseOrchestrator` |

### 2. Sample data

Both apps look for demo files in `../backend/sample_data/` via a `__file__`-anchored `BACKEND_DIR` constant, so you can `streamlit run` from anywhere:

- `backend/sample_data/braf_v600e.tsv` — default demo input for `app.py`.
- `backend/sample_data/luna_pathology.pdf` + `backend/sample_data/luna_tumor.vcf` — bundled Luna demo for `app_agent.py`.

If those files are missing, regenerate the Luna PDF with `python backend/scripts/generate_luna_pdf.py`.

### 3. Output / upload directory

`app_agent.py` writes user-uploaded PDFs and VCFs to `../backend/out/uploads/` (created on demand). That's also where the orchestrator and CLI drop `case.json` artifacts, so cleanup is one directory.

### 4. Credentials (`.env`)

`app_agent.py` calls `load_dotenv()` with no path, so it reads `.env` from the current working directory. Easiest options:

- **Run streamlit from `frontend/`** and symlink: `ln -s ../backend/.env .env`
- **Run streamlit from `backend/`**: `streamlit run ../frontend/app_agent.py` (picks up `backend/.env` natively).

Keys read from `.env`:

- `ANTHROPIC_API_KEY` — used by `agent/pathology.py`, `agent/emails.py`, `agent/explain.py` for direct LLM calls. Heuristic fallbacks kick in if missing. The Claude Agent SDK itself defaults to the `claude` CLI subprocess transport, which reuses Claude Code's auth.
- `GOOGLE_PLACES_API_KEY` — real lab / vet / vendor geo lookups in `agent/labs.py`. Without it, only curated static results are returned.
- `NEOVAX_MODEL` — override the orchestrator model (default `claude-sonnet-4-5`; `claude-opus-4-6` for highest quality).

### 5. Gmail sign-in (optional — `app_agent.py` only)

Email **drafting** works with no extra setup. To actually **send** drafts via the "Send via Gmail" button, the app uses the OAuth installed-app flow in `backend/src/neoantigen/agent/gmail_auth.py`:

- Provide a Desktop-app OAuth client secrets JSON at `~/.config/neovax/client_secret.json` (override with `NEOVAX_GOOGLE_CLIENT_SECRET`).
- While the OAuth consent screen is unverified, add any demo recipient addresses as **test users** in GCP Console.
- Scopes requested: `gmail.send`, `userinfo.email`. Sender email is auto-discovered via `gmail.users.getProfile` — no env var needed.
- Token cache: `$NEOANTIGEN_CACHE/gmail_token.json` (override with `NEOVAX_GMAIL_TOKEN`). "Sign out" deletes it.
- Headless servers can't run the consent flow — sign in once on a workstation, then copy the token file.

## Running

```bash
# plain dashboard
cd frontend && streamlit run app.py

# agent dashboard
cd frontend && streamlit run app_agent.py
```

The plain dashboard has no hard external-service dependencies (APIs are opt-in via the "Query ClinicalTrials.gov + DGIdb" checkbox). The agent dashboard will run end-to-end with heuristic fallbacks even if `ANTHROPIC_API_KEY` and Google creds are absent — just with lower-quality output.
