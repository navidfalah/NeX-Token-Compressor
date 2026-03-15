# Firma-KI — AI API Gateway & NEX Compression Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-Proprietary-red)]()

**Firma-KI** is an enterprise-grade AI proxy gateway that sits between your application and any LLM (DeepSeek, Gemini, OpenAI, Anthropic, Grok). It intercepts every prompt, compresses it using deterministic algorithms, routes it to the cheapest capable model, and audits every token — dramatically reducing AI API costs.

---

## 🎯 Main Goal

> **Ship the same intelligence for a fraction of the token cost.**

Every request that enters the gateway is aggressively compressed before it reaches any paid AI API. The core claim: **60–90% token reduction** on typical enterprise workloads — verified per-request in the analytics dashboard.

---

## 🏗 Architecture Overview

```
Your App → [Firma-KI Gateway]
               │
               ├─ Stage 1: NEX Compression  (input-side)
               │   ├── Code:  AST Prune → Type Erase → Comment Strip → Dead Code Eliminate
               │   └── Text:  Stop-word Prune → Redundancy Eliminate → TF-IDF Extract → NEX S1 Filter
               │
               ├─ Stage 2: Cascade Router  (model selection)
               │   ├── Tier 1 — cheap/fast (DeepSeek): simple queries, facts, summaries
               │   └── Tier 2 — powerful (Gemini/GPT-4o): complex reasoning, code generation
               │
               ├─ Stage 3: AI Provider Call  (external API)
               │
               └─ Stage 4: Output Normalisation  (output-side)
                   ├── Code:  Fence Strip → Trailing Comment Remove → Whitespace Normalise
                   └── Text:  Preamble Strip → Caveat Reduce → Qualifier Normalise → Tail Strip
```

---

## ✨ Feature Map

### 1. Dynamic Cascade Routing
Deterministic complexity scoring routes every request to the **cheapest model that can handle it**:
- **Tier 1 (cheap)** — DeepSeek or any configured lightweight provider: simple questions, factual retrieval
- **Tier 2 (powerful)** — Gemini Pro / GPT-4o: multi-step reasoning, code generation, analysis
- Configurable `confidence_threshold` per API key; escalation logged in real-time

### 2. NEX Code Compression (`services/gateway/compression/nex_code_compressor.py`)
Seven deterministic input-side algorithms for source code:

| Algorithm | What it removes |
|---|---|
| Python AST Prune | Docstrings via CPython parse tree |
| Type Annotation Erase | `: int`, `-> str` hints |
| Comment Pruner | `#`, `//`, `/* */`, `--`, `<!-- -->` |
| Dead Code Eliminate | Lines after `return`/`raise` |
| Import Deduplicate | Duplicate import lines |
| Whitespace Compact | Trailing spaces, repeated blank lines |
| Markdown Fence Strip | ` ```python ``` ` wrappers |

Four output-side algorithms normalise AI-generated code before delivery.

### 3. NEX Text Compression (`services/gateway/compression/nex_text_compressor.py`)
Seven deterministic input-side algorithms for natural language:

| Algorithm | Technique |
|---|---|
| NEX S1 Semantic Filter | Signal-keyword density scan (fastest) |
| TF-IDF Extractor | Statistical sentence importance ranking |
| Stop-word Pruner | Remove grammatical filler words |
| Redundancy Eliminator | Jaccard similarity dedup (>70% overlap) |
| Chunk Summarizer | First 2 sentences per 150-word block |
| Hedge Word Remover | "I think", "perhaps", "maybe" removed |
| Quotation Compressor | Long inline quotes trimmed to 20 words |

Five output-side algorithms clean AI preambles, caveats, and closing pleasantries.

### 4. Analytics Dashboard (`/dashboard/analytics`)
Real-time metrics from every API call stored in `AuditLog`:
- Tokens in / out / saved per request
- Cost per API call (actual vs. estimated without compression)
- Breakdown by AI provider and API key
- Configurable filters: period, status, source, API key
- Expandable per-row input/output payload viewer

### 5. AI Provider Management (`/dashboard/providers`)
Add and manage any AI provider:
- DeepSeek, OpenAI, Google Gemini, Anthropic Claude, xAI Grok, Custom endpoints
- Set default / active provider
- Per-provider usage stats (requests, tokens, bytes)
- Masked API key display

### 6. API Key Management (`/dashboard/api-keys`)
Issue gateway API keys for your apps:
- Per-key rate limiting (req/min)
- Enable/disable compression and caching per key
- Link a key to a specific provider (bypass routing)
- One-time key reveal on creation, then only masked

### 7. Token Telemetry & Security Audit
- Immutable `AuditLog` record for every request
- Full original payload, compressed payload, AI response, translated response stored
- PII masking pipeline (Privacy Hub) — sensitive data masked before dispatch
- BSI-compliant audit trail

### 8. Pipeline Monitor & Test Playground
- Interactive pipeline runner: submit a prompt, watch every stage execute step by step
- Displays: tokens used, compression ratio, algorithm selected, model chosen, latency
- Algorithm selector: choose which input/output algorithm to apply before running
- No fake data — all results come from real compression logic

### 9. Team & Access Control
- Multi-user organizations
- Role-based access (admin / user)
- Email invitation flow
- Per-user activity tracking

---

## 🚀 Quick Start

### 1. Install
```bash
git clone <repo>
cd FirmaKI-Nex
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure
Create `.env`:
```env
SECRET_KEY=your-secret-key-here
DEEPSEEK_API_KEY=sk-...
GEMINI_API_KEY=...
DATABASE_URL=sqlite+aiosqlite:///./db.sqlite3
```

### 3. Run
```bash
uvicorn main:app --reload
```

Dashboard: **http://127.0.0.1:8000/dashboard**

---

## 📡 Gateway API Usage

Send any prompt through the gateway using your API key:

```bash
curl -X POST http://localhost:8000/api/gateway/chat \
  -H "Authorization: Bearer fk-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain async/await in Python"}],
    "stream": false
  }'
```

The gateway will:
1. Classify the payload (code vs. text)
2. Apply appropriate compression algorithms
3. Route to the cheapest capable model
4. Return the normalised response + telemetry headers

Response includes headers:
- `X-Tokens-Original` — tokens before compression
- `X-Tokens-Compressed` — tokens sent to AI
- `X-Model-Used` — which AI provider was selected
- `X-Cost-USD` — actual API cost

---

## 📁 Project Structure

```
FirmaKI-Nex/
├── api/routers/
│   ├── dashboard.py        # All dashboard routes (analytics, keys, providers, …)
│   └── gateway.py          # External-facing API gateway endpoint
├── models/
│   ├── dashboard.py        # APIKey, AIProvider, AuditLog, CascadeConfig, …
│   └── accounts.py         # User, Organization, Invitation
├── services/gateway/
│   ├── nex_pipeline.py     # 3-stage NEX pipeline orchestrator
│   ├── cascade_router.py   # Complexity scoring + model selection
│   └── compression/
│       ├── nex_code_compressor.py   # Code input/output compression
│       ├── nex_text_compressor.py   # NL text input/output compression
│       ├── cac_compressor.py        # AST-based code compression (CAC)
│       └── nlc_compressor.py        # SCOPE/EHPC NL compression
├── templates/dashboard/    # Jinja2 HTML templates
└── main.py                 # FastAPI app entry point
```

---

## 🔬 NEX Philosophy

**NEX (Network Execution)** is the machine-native intermediate representation at the heart of Firma-KI. The five rules:

1. **Token Minimization** — every byte of prompt that can be removed without information loss, must be removed
2. **Machine-Native First** — compress to the smallest representation the AI can still parse
3. **Determinism** — all compression algorithms are pure functions with no randomness
4. **Separation of Sides** — input-side and output-side pipelines are independent
5. **Absolute Auditability** — every token, cost, and routing decision is logged

---

*Built for enterprise AI workloads. Zero fake data. Every metric is real.*
