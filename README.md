# Firma-KI Nex: Enterprise AI API Gateway & Compression Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-Proprietary-red)]()

**Firma-KI Nex** is a pioneering, enterprise-grade AI proxy gateway designed to sit securely between your proprietary applications and leading Large Language Models (DeepSeek, Gemini, OpenAI, Anthropic). 

It intercepts every prompt, aggressively compresses it using deterministic **NEX algorithms**, intelligently routes it to the most cost-effective capable model, and thoroughly audits every token—dramatically reducing AI API costs by up to 60-90% without sacrificing output quality.

---

## 🎯 Our Mission & Value Proposition

> **Ship the same intelligence for a fraction of the token cost.**

In the era of Generative AI, token costs and latency scale linearly with usage. Firma-KI solves the scaling bottleneck for enterprises by acting as a highly optimizedmiddleware layer. By compressing both code and natural language inputs *before* they hit a paid API, Firma-KI drastically reduces operational overhead, minimizes latency, and maximizes ROI on AI infrastructure.

---

## 🏗 System Architecture & The 3-Stage NEX Pipeline

Firma-KI operates on a robust, asynchronous **3-Stage NEX Pipeline** (`services/gateway/nex_pipeline.py`) that processes all traffic in real-time.

```text
Your Enterprise Application
            │
            ▼
[ Firma-KI Nex API Gateway ]
            │
   ┌────────┴────────┐
   │                 │
   ▼                 ▼
Stage 1: Input Compression (NEX Code & Text)
Aggressively strips syntax, reduces semantic redundancy, and minifies data deterministically.
   │                 │
   ▼                 ▼
Stage 2: Dynamic Cascade Routing
Evaluates payload complexity and routes simple queries to Tier-1 models (e.g., DeepSeek) 
and complex reasoning queries to Tier-2 models (e.g., Gemini 2.5 Flash / GPT-4o).
   │                 │
   ▼                 ▼
[ AI Provider Call - External API ]
   │                 │
   ▼                 ▼
Stage 3: Output Decompression & Normalization
Reconstructs formatted code, restores natural language syntax, and cleans AI diatribes.
   │                 │
   ▼                 ▼
Application Response (JSON / Full Stream)
```

---

## ✨ Core Technical Features

### 1. Dynamic Cascade Intelligence Routing
Firma-KI employs deterministic complexity scoring to route every request to the **cheapest model that can handle it reliably**. It supports seamless failover and load balancing across providers.
* **Tier 1 (High Speed, Low Cost):** E.g., DeepSeek—optimized for factual retrieval, simple summaries, and routine transformations.
* **Tier 2 (High Reasoning):** E.g., Gemini Pro, GPT-4o—triggered automatically for complex logic, multi-step reasoning, and advanced code generation.
* **Configurable Thresholds:** Enterprise admins can adjust confidence thresholds per API key.

### 2. Advanced Algorithmic Compression
Firma-KI utilizes proprietary input/output algorithms to minimize token footprint.

**For Source Code (`nex_code_compressor.py`):**
* **AST Pruning:** Parses CPython trees to strip docstrings and unused definitions natively.
* **Type Annotation Erasure:** Safely removes Python type hints (`: int`, `-> str`) prior to submission.
* **Identifier Minification:** Shortens lengthy variable and function names to single characters mapping the logic.
* **Control Flow Minimization:** Strips redundant whitespace and compacts syntax tokens.

**For Natural Language (`nex_text_compressor.py`):**
* **Semantic Keyword Extraction (NEX S1):** Extracts high-signal keywords and logic maps using regex and NLP heuristics.
* **Redundancy Elimination:** Jaccard similarity deduplication removes repetitive context blocks.
* **Corporate Dictionary Mapping:** Compresses known enterprise terminology into dense acronyms.
* **TF-IDF Summarization:** Ranks sentences by statistical importance to drop filler.

### 3. Comprehensive Analytics & Audit Dashboard
Built with FastAPI and a beautiful Glassmorphism dashboard UI:
* **Real-time Telemetry:** Tracks tokens sent, tokens saved, and precise USD cost per request.
* **Intelligent Pagination:** Efficiently queries millions of audit logs to display historical data.
* **PDF Business Reports:** Export stunning, enterprise-branded PDF reports summarizing token savings, provider usage, and AI efficiency over custom date ranges.

### 4. Enterprise Security & API Management
* **Role-Based Access Control (RBAC):** Admin/User hierarchy for organization management.
* **API Key Lifecycle:** Issue, revoke, and rate-limit internal API keys globally or per-provider.
* **Privacy Engine:** Ensures sensitive tokens are handled securely before transit.

---

## 🚀 Quick Start Guide

### Prerequisites
* Python 3.10+
* Virtual Environment
* Node.js (Optional, for advanced UI asset compiling)

### 1. Installation Environment
```bash
git clone <repo_url>
cd FirmaKI-Nex
python -m venv venv 
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration (`.env`)
Create a `.env` file in the root directory:
```env
SECRET_KEY=your_secure_secret_key
DATABASE_URL=sqlite+aiosqlite:///./db.sqlite3
DEEPSEEK_API_KEY=sk-your-deepseek-key
GEMINI_API_KEY=your-gemini-key
```

### 3. Launching the Nexus
```bash
uvicorn main:app --reload --port 8000
```
Navigate to the interactive dashboard: **[http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)**

---

## 📡 Developer API Usage

The system exposes a unified `/api/gateway/chat` endpoint. Send massive payloads using your issued API key; the Gateway automatically compresses, routes, and answers you.

```bash
curl -X POST http://localhost:8000/api/gateway/chat \
  -H "Authorization: Bearer fk-your-secure-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "system", "content": "You are a helpful coding assistant. Provide minimal explanations."},
      {"role": "user", "content": "Explain async and await in Python thoroughly with examples."}
    ],
    "stream": false
  }'
```

**Response Telemetry Headers Attached:**
- `X-Tokens-Original` — Payload size before Firma-KI intervention.
- `X-Tokens-Compressed` — Actual tokens sent/billed by external AI.
- `X-Cost-USD` — Calculated precise cost.
- `X-Compression-Algorithm` — The specific NEX algorithm applied to your input.

---

## 📁 Repository Structure

```text
FirmaKI-Nex/
├── api/
│   ├── routers/
│   │   ├── dashboard.py        # Glassmorphic UI & Analytics Routes
│   │   └── gateway.py          # Core AI Proxy & Endpoint Ingestion
├── models/
│   ├── accounts.py             # RBAC Users & Organizations DB schema
│   └── dashboard.py            # AuditLogs, APIKeys, Provider tracking
├── services/
│   ├── gateway/
│   │   ├── nex_pipeline.py     # 3-Stage NEX Pipeline Orchestrator
│   │   ├── cascade_router.py   # Decision engine for Cascade Routing
│   │   └── compression/        
│   │       ├── nex_code_compressor.py 
│   │       └── nex_text_compressor.py 
├── templates/                  # Jinja2 Frontend (Tailwind/DaisyUI)
└── main.py                     # FastAPI ASGI Server
```

---

## 🔬 The NEX Philosophy

**NEX (Network Execution)** is the core machine-native design philosophy behind Firma-KI mapping the future of AI infra:
1. **Token Minimization:** Eliminate every byte natively without losing reasoning capability.
2. **Machine-Native Context:** AI models do not require human-readable text; they require semantic math.
3. **Deterministic Application:** Compression is governed by syntax and AST math, never random stochastic loss.
4. **Absolute Auditability:** What you save is what you see. Complete accounting for every token intercepted.

*Designed for the Modern Enterprise AI Stack. Zero fake metrics. Mathematical verifiable efficiency.*
