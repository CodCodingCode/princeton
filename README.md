<p align="center">
  <img src="frontend/public/doctor-poster.png" alt="Onkos" width="640" />
</p>

<h1 align="center">Onkos</h1>

<p align="center">
  <em>A cursor for oncologists. Drop a folder of clinical PDFs, get an NCCN-grounded treatment plan, matched Regeneron trials, and a talking avatar cockpit in 90 seconds.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-black" alt="MIT" />
  <img src="https://img.shields.io/badge/python-3.11%2B-black" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/next.js-15-black" alt="Next.js 15" />
</p>

## What it does

Drop a folder of messy patient records (PDFs, scanned pathology, intake CSVs, imaging notes) and Onkos:

1. **Extracts** every oncology-relevant field (diagnosis, stage, biomarkers, mutations, ECOG, prior therapies) using a self-hosted vision language model for scanned pages and Kimi-K2 for the structured cleanup.
2. **Walks an NCCN-grounded treatment railway** with K2-Think v2, streaming `<think>` tokens live so the oncologist can watch the model deliberate, with every recommendation grounded in PubMed citations from a Chroma RAG corpus.
3. **Matches Regeneron-sponsored clinical trials** against the patient using structured eligibility predicates, then geocodes recruiting sites on a live Google Map.
4. **Generates a downloadable oncologist report** (ReportLab PDF) with diagnosis, plan, citations, and ranked trial matches.
5. **Drives a live avatar cockpit** powered by Kimi-K2: the oncologist talks to a HeyGen/LiveAvatar, asks "why this drug?" or "show me the trial in Boston," and Kimi both answers and navigates the UI via tool calls.

There's also a plain-English **patient view** at `/patient` that retells the same case data: "Your diagnosis," "Your plan," "How to heal," "Next steps," "Questions to ask your oncologist." Same backend, same SSE stream, different audience.

## Model stack (the flex)

- **MediX-R1-30B VLM** from MBZUAI, a 30-billion-parameter medical vision language model we self-host on a GH200 GPU via vLLM over an SSH tunnel. Not a hosted API call, we run the weights. This is what lets us read scanned pathology that pure-text extraction misses.
- **K2-Think v2** from MBZUAI for the NCCN treatment reasoning, with `<think>` blocks streamed live to the UI so the chain of reasoning is auditable, not a black box.
- **Kimi-K2** as the agentic conversational layer, wired through LangGraph with conversation memory, RAG retrieval, and a `chat_ui_focus` tool that literally drives the frontend (changes tabs, focuses trials by NCT ID, scrolls the railway).

Each model does what it's best at. The user experiences them as a single coherent assistant they can talk to out loud.

## Regeneron integration

Onkos was built with the Regeneron pipeline as the first-class trial source, not an afterthought.

- **29 recruiting Regeneron trials scraped live from ClinicalTrials.gov v2.** The [`scripts/scrape_regeneron_trials.py`](backend/scripts/scrape_regeneron_trials.py) script emits one Python file per trial under [`backend/src/neoantigen/external/regeneron/`](backend/src/neoantigen/external/regeneron/). Re-running it refreshes the entire registry in one command.
- **Real structured eligibility engine, not regex.** [`regeneron_rules.py`](backend/src/neoantigen/external/regeneron_rules.py) evaluates every case across typed predicates: AJCC stage buckets, biomarker gates (BRAF V600, EGFR, ALK, ROS1, MET exon 14, KRAS G12C, HER2, BRCA, MSI-high, PD-L1 TPS, LAG-3), prior systemic and anti-PD-(L)1 therapy, ECOG 0-1, RECIST measurable disease, age bounds. Every gate returns `pass`, `fail`, or `needs_more_data`.
- **Geocoded sites.** [`external/trial_sites.py`](backend/src/neoantigen/external/trial_sites.py) pulls the site list for every matched trial and geocodes it via Google Maps. The cockpit renders pins next to the trial card.
- **Downloadable Regeneron-ready report.** ReportLab packet with the full plan, PubMed citations, and every trial's eligibility gates annotated.

Full writeup in [`resources/DEVPOST.md`](resources/DEVPOST.md).

## Quickstart

```bash
# Backend (from repo root)
pip install -e './backend[agent,web,pdf-vision,rag]'
neoantigen serve --reload           # FastAPI on http://localhost:8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                         # Next.js on http://localhost:3000
```

Open [http://localhost:3000](http://localhost:3000) and drop a PDF on the upload page.

Check dependency wiring at any time with `GET /api/health`, which reports which optional services (K2, Kimi, Google Maps, RAG store, MediX VLM) are live.

## Environment variables

Put these in `backend/.env`. The CLI loads it via `python-dotenv`.

**Required for the full experience:**

| Var                               | Purpose                                                         |
| --------------------------------- | --------------------------------------------------------------- |
| `K2_API_KEY`                      | Medical reasoning model (K2-Think v2)                           |
| `KIMI_API_KEY`                    | Avatar brain + chat endpoint; `/chat` returns 503 when unset    |
| `GOOGLE_MAPS_API_KEY`             | Server-side geocoding for trial sites                           |
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Client-side map rendering in `TrialMap`                         |
| `LIVEAVATAR_API_KEY`              | LiveAvatar video stream (replaces retired HeyGen Streaming API) |
| `LIVEAVATAR_AVATAR_ID`            | LiveAvatar avatar to drive                                      |

**Optional (with sensible defaults or silent fallbacks):**

| Var                                                | Purpose                                                          | Default                     |
| -------------------------------------------------- | ---------------------------------------------------------------- | --------------------------- |
| `K2_BASE_URL`                                      | OpenAI-compatible base URL for the medical model                 | `https://api.k2think.ai/v1` |
| `NEOVAX_MODEL`                                     | Served model name                                                | `MBZUAI-IFM/K2-Think-v2`    |
| `NEOVAX_LOG_PATH`                                  | Every model call logged here (check first when output looks off) | `backend/out/k2.log`        |
| `NEOVAX_BACKEND_URL`                               | Frontend proxy target                                            | `http://localhost:8000`     |
| `NEOVAX_CORS_ORIGINS`                              | Comma-separated backend allowlist                                | `localhost:3000,5173`       |
| `MEDIX_API_KEY` / `MEDIX_BASE_URL` / `MEDIX_MODEL` | Self-hosted MediX-R1-30B VLM via vLLM                            | unset                       |

The orchestrator never hard-fails. Missing key, missing RAG store, scanned PDF without `pdf-vision`: every path degrades to `needs_more_data` and keeps going. Full env table and fallback map in [`CLAUDE.md`](CLAUDE.md).

## Repo layout

```
backend/            neoantigen Python package, FastAPI + SSE, Typer CLI
  src/neoantigen/
    agent/          PatientOrchestrator + event bus + LLM client
    nccn/           dynamic treatment-railway walker
    external/       Regeneron registry, ClinicalTrials.gov, trial sites
    rag/            Chroma PubMed store
    chat/           LangGraph Kimi agent
    web/            FastAPI routes + SSE storage
    report/         ReportLab oncologist PDF
  scripts/          scrape_regeneron_trials.py, build_pubmed_rag.py
  test_fixtures/    full real-world case (pathology, imaging, chemo PDFs, ground truth)
frontend/           Next.js 15 + Tailwind cockpit
  app/              /upload, /case/[id], /patient
  components/       AvatarPanel, CaseTabs, RailwayMermaid, TrialMap, ...
resources/          DEVPOST.md submission + onkos_pitch.pptx
LICENSE             MIT
```

## Request flow

`POST /api/cases` (multipart PDF) hits the `PatientOrchestrator`. It extracts oncology fields (pypdf first, MediX VLM fallback on scans, Kimi cleanup), walks the NCCN railway with K2-Think (streaming `<think>` tokens), evaluates every Regeneron trial against the case, geocodes matched sites via Google Maps, and publishes every step on an asyncio event bus. The frontend subscribes to `GET /api/cases/{id}/stream` (SSE) and updates the cockpit live. The report PDF is built lazily on `GET /report.pdf`. The LangGraph chat agent (`POST /chat`) gets a slimmed case snapshot per turn and drives the UI through `chat_ui_focus` tool calls.

Deeper dive in [`backend/CLAUDE.md`](backend/CLAUDE.md).

## Deeper docs

- [`CLAUDE.md`](CLAUDE.md): full architecture, env vars, silent-fallback table, frontend cockpit wiring.
- [`backend/CLAUDE.md`](backend/CLAUDE.md): orchestrator internals, event bus fanout, LLM layer, design decisions.
- [`resources/DEVPOST.md`](resources/DEVPOST.md): the full Regeneron Track and Best Use of Kimi-K2 Track writeups.

## License

MIT. See [`LICENSE`](LICENSE).
