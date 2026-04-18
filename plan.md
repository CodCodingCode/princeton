# NeoVax × MediX-R1-30B on GH200 — Integration Plan

## 1. What NeoVax is (context for why we need a medical LLM)

NeoVax is a personalized cancer vaccine pipeline for pets (canine, extensible to human). Input: tumor VCF + pathology PDF. Output: ranked neoantigen peptides + an mRNA vaccine construct + a full "case file" (drugs, trials, labs, vets, emails, timeline, owner-facing explanation).

The pipeline has two orthogonal AI layers:

- **Agent orchestrator** — Claude Agent SDK drives 11 tools (pathology → pipeline → drug/trial search → lab/vet finder → structure validation → email drafts → timeline → owner explanation). Lives in [backend/src/neoantigen/agent/orchestrator.py](backend/src/neoantigen/agent/orchestrator.py). Uses Anthropic's tool-use protocol. **Not touching this.**
- **Direct LLM calls** for three medical-reasoning tasks, all already routed through a single factory in [backend/src/neoantigen/agent/\_llm.py](backend/src/neoantigen/agent/_llm.py). **This is what we're swapping.**

## 2. The three LLM call sites

All three use `pydantic_ai.Agent` with the same `build_model()` from `_llm.py`. One backend change flips all three.

| File                                                                                   | Task                                                                                                       | Why medical expertise helps                                                            |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [backend/src/neoantigen/agent/pathology.py](backend/src/neoantigen/agent/pathology.py) | Parse pathology PDF → typed `PathologyReport` (cancer type, grade, breed, location, prior tx, DLA alleles) | Must recognize veterinary oncology vocabulary, grading systems, breed-specific cancers |
| [backend/src/neoantigen/agent/emails.py](backend/src/neoantigen/agent/emails.py)       | Draft clinical emails to sequencing labs, vet oncologists, mRNA vendors, ethics boards, owners             | Must use correct clinical terminology and treatment context                            |
| [backend/src/neoantigen/agent/explain.py](backend/src/neoantigen/agent/explain.py)     | Turn a case file into a 400-500 word plain-English explanation for the pet owner                           | Must reason over cancer biology accurately, then translate without losing truth        |

Today these are wired to K2 Think V2 via the OpenAI-compatible endpoint at `api.k2think.ai/v1`. K2 is a general reasoning model — fine but not medical. **MediX-R1-30B is medical-RL-trained and should outperform on every one of these tasks.**

## 3. Why MediX-R1-30B specifically

From MBZUAI's HuggingFace org ([huggingface.co/MBZUAI](https://huggingface.co/MBZUAI)):

- **[MBZUAI/MediX-R1-30B](https://huggingface.co/MBZUAI/MediX-R1-30B)** — 31B image-text-to-text, RL-trained on medical data. Their flagship medical reasoning model. ⭐ **pick this**
- Alternatives considered:
  - MediX-R1-8B / 2B — smaller variants, fallback if 30B latency bites
  - MedMO-8B-Next (newer, updated 9 days ago) — image-text-to-text medical, good second-opinion for pathology extraction
  - Video-CoM, dialseg-ar, JAIS/Nanda/Sherkala — not medical, skip
- All open weights on HF, no API gatekeeping.

## 4. Hardware plan — GH200

MediX-R1-30B is ~60 GB in fp16 / ~30 GB in int8. GH200 specs:

- Grace CPU (72 ARM Neoverse V2 cores) + H100 GPU
- 96 GB HBM3 (base) or 144 GB HBM3e (newer SKU) on the GPU alone
- NVLink-C2C at 900 GB/s between CPU and GPU (unified memory)

**Conclusion**: 30B fits single-GPU in bf16 with ~30 GB headroom for KV cache. No tensor parallelism needed. Expect ~40–80 tok/s decode.

### GH200 gotchas

- **ARM64** (aarch64), not x86. Pick ARM-compatible wheels.
- Use the NGC container to skip wheel-hunting: `nvcr.io/nvidia/pytorch:24.10-py3` ships ARM + CUDA 12.6 correctly wired.
- vLLM has official ARM support from 0.6.x onward. If prebuilt wheels fail, build from source with `CUDA_HOME` set and `MAX_JOBS=8`.

## 5. Serving setup — vLLM on GH200

vLLM gives us an OpenAI-compatible endpoint, which is exactly what `_llm.py` already expects. **Zero code changes** in the three call sites.

```bash
# Option A: bare metal (after pip install vllm on the GH200)
vllm serve MBZUAI/MediX-R1-30B \
  --port 8000 \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --served-model-name medix-r1-30b

# Option B: NGC container (recommended — avoids ARM wheel pain)
docker run --gpus all --rm -it \
  -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  nvcr.io/nvidia/pytorch:24.10-py3 \
  bash -c "pip install vllm && \
    vllm serve MBZUAI/MediX-R1-30B \
      --port 8000 --dtype bfloat16 \
      --max-model-len 8192 \
      --served-model-name medix-r1-30b --host 0.0.0.0"
```

First launch downloads ~60 GB of weights from HF → takes a few minutes. Cache mount makes subsequent runs instant.

Verify the endpoint works:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "medix-r1-30b",
    "messages": [{"role":"user","content":"What is a BRAF V600E mutation and why does it matter in melanoma?"}],
    "max_tokens": 256
  }'
```

## 6. Client-side wiring (NeoVax side)

All three call sites already route through [backend/src/neoantigen/agent/\_llm.py](backend/src/neoantigen/agent/_llm.py). Today it points at K2. We swap it to our vLLM endpoint **via env vars — no code edits required**.

On the machine running NeoVax (laptop / demo box, NOT the GH200):

```bash
# in backend/.env or exported before running
export K2_API_KEY="dummy"                              # vLLM ignores it but _llm.py requires it be set
export K2_BASE_URL="http://<gh200-host>:8000/v1"       # we'll add support for this env var — see below
export NEOVAX_MODEL="medix-r1-30b"
```

### Tiny code change needed in `_llm.py`

Right now `K2_BASE_URL` is a module-level constant. Make it overridable via env so we don't have to fork the file:

```python
# _llm.py line 13
K2_BASE_URL = os.environ.get("K2_BASE_URL", "https://api.k2think.ai/v1")
```

That's the entire code diff on the NeoVax side. One line.

## 7. Validation — prove it works before the demo

Run these in order on the NeoVax box after pointing at the GH200:

```bash
# 1. Pipeline sanity (no LLM involved, just confirms nothing else broke)
.venv/bin/neoantigen demo

# 2. Pathology extraction hits the new model
.venv/bin/python -c "
import asyncio
from pathlib import Path
from neoantigen.agent.pathology import extract_pathology
r = asyncio.run(extract_pathology(Path('backend/sample_data/luna_pathology.pdf')))
print(r.model_dump_json(indent=2))
"

# 3. End-to-end agent run
.venv/bin/neoantigen agent-demo \
  --pdf backend/sample_data/luna_pathology.pdf \
  --vcf backend/sample_data/luna_tumor.vcf

# 4. Streamlit live UI (from frontend/)
cd frontend && streamlit run app_agent.py
```

### Smoke-test checklist

- [ ] `curl` against vLLM returns a plausible medical answer
- [ ] `PathologyReport` fields populate correctly on `luna_pathology.pdf` (patient=Luna, cancer_type, breed, location, prior_treatments)
- [ ] `explain_case_to_owner` output is warmer + more accurate than K2's version (subjective, but judge vs. the current baseline)
- [ ] Emails come out structured with correct clinical terminology
- [ ] Latency per call: aim for < 15s for pathology extract, < 10s for email, < 20s for explain (at bf16, 8k ctx)

## 8. Risks & fallbacks

| Risk                                                               | Mitigation                                                                                                                                                                                                                         |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| MediX-R1-30B doesn't emit clean JSON → PydanticAI validation fails | `extract_pathology` already has a regex heuristic fallback ([pathology.py:132](backend/src/neoantigen/agent/pathology.py#L132)). If fails often, add a system-prompt reminder: "Respond ONLY with valid JSON matching the schema." |
| vLLM ARM build fails on GH200                                      | Use the NGC container (Option B above). It's the official NVIDIA image and known-good on GH200.                                                                                                                                    |
| Weights download stalls (slow HF mirror)                           | Pre-download: `huggingface-cli download MBZUAI/MediX-R1-30B --local-dir ~/models/medix-r1-30b`, then point vllm at the local dir.                                                                                                  |
| Model is image-text-to-text but we're feeding it pure text         | That's fine — it accepts text-only too. The image capability is a bonus if we later pass the raw pathology PDF pages as images for higher-fidelity extraction.                                                                     |
| Network latency from laptop → GH200 cancels out inference speed    | Either run the Streamlit app ON the GH200, or tunnel over SSH: `ssh -L 8000:localhost:8000 gh200-host`.                                                                                                                            |

## 9. Order of operations on the GH200 machine

1. `git clone` this repo onto the GH200 (or just `scp plan.md` if you're doing serving only).
2. Install Docker + NVIDIA container toolkit (skip if already present).
3. Pre-pull the weights to avoid timing out the first `vllm serve`:
   ```bash
   pip install -U huggingface_hub
   huggingface-cli download MBZUAI/MediX-R1-30B --local-dir ~/models/medix-r1-30b
   ```
4. Launch vLLM (Option B container above, but swap the HF model id for the local path `--model ~/models/medix-r1-30b`).
5. `curl` the endpoint from the GH200 itself to confirm it serves.
6. Open port 8000 OR set up an SSH tunnel from the laptop.
7. On the laptop: add `K2_BASE_URL` + `NEOVAX_MODEL` + `K2_API_KEY=dummy` to `backend/.env`.
8. Apply the one-line change in [backend/src/neoantigen/agent/\_llm.py:13](backend/src/neoantigen/agent/_llm.py#L13) to read `K2_BASE_URL` from env.
9. Run the validation checklist in §7.

## 10. Stretch — if we have time

- **Quantize to int8 with AWQ/GPTQ** → cut VRAM to ~30 GB, double throughput, free up room for bigger KV cache and concurrent requests.
- **Feed pathology as images, not text.** MediX-R1 is VLM-native. PDF → page PNGs → direct vision input may extract fields the text-layer misses (handwritten notes, tables with merged cells). Replace `_extract_text_from_pdf` with a PDF-to-image step in [pathology.py](backend/src/neoantigen/agent/pathology.py).
- **A/B against MedMO-8B-Next** on a held-out set of pathology PDFs. Cheaper to run, may be competitive.
