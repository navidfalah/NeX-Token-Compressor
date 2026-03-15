# Firma-KI: Next-Gen AI Gateway & Semantic Compressor

Firma-KI is an enterprise-grade AI proxy gateway, security firewall, and semantic network optimizer designed to intercept, compress, and accelerate outbound interactions with Large Language Models (LLMs). It dramatically reduces API costs (up to 97%) by transmuting conversational bloat into highly dense NEX bytecode.

## 🌟 Core Architecture (NEX Pipeline)

The Firma-KI engine fundamentally alters the way applications talk to AI models through a 3-Stage NEX Bytecode Pipeline:

1. **Stage 1 (Compressor):** A fast, local/cheap AI model reads the user's bloated prompt. It semantically crushes the prompt into ultra-dense **NEX Bytecode** (e.g. `[FACT:x=y]`, `[CMD:Summarize]`).
2. **Stage 2 (The Middle AI):** The commercial AI (e.g. DeepSeek-Coder, GPT-4) receives the compressed NEX Bytecode. Because the token count is reduced by 60-90%, the commercial AI processes the logic lightning-fast and costs fractions of a cent, returning its answer in the same dense NEX Bytecode format.
3. **Stage 3 (Human Translator):** An expander model intercepts the returning bytecode and translates the dense logic back into a beautifully formatted, natural-sounding human response. Structural data like Code and JSON are gracefully passed through natively.

## 🚀 Advanced Gateway Capabilities

*   **Dual-Engine Generative Compression (NLC / CAC):** Operates using lossless semantic extraction. No mathematical condition, variable, or core instruction is lost during compression.
*   **Confidence-Driven Cascade Routing:** Dynamically routes complex logic requests to heavier models (like GPT-4o) and simpler extractions to lightning-fast models (like DeepSeek).
*   **Domain-Specific Semantic Caching:** Utilizes Vector Databases/Embeddings to instantly intercept and serve responses to geometrically similar questions.
*   **Edge-Native Processing Nodes:** Manage geographic processing zones for data sovereignty (e.g., German-only datacenters).
*   **Centralized MCP Gateway:** Unified integration point for External Tooling / Model Context Protocol.
*   **Financial Efficiency Tracking:** Live telemetry mapping your token payloads against high-cost commercial baselines.

## 🌐 Enterprise Scalability Features

* **Sovereign Cloud Integrations:** Support for Aleph Alpha, Open Telekom Cloud, and Hetzner.
* **BSI-Compliant Logging:** Immutable audit trails and cryptographic signatures.
* **Works Council Compliance:** Advanced anonymization modes (GDPR).
* **Liability Scoring:** "Confidence & Risk" badges for AI-generated output.

## 🛠 Usage & Dashboard

*   **Main Dashboard (`/dashboard`)**: Monitor cost metrics and global token burn.
*   **Security Audit (`/dashboard/audit`)**: Configure PII masking and review security pipeline executions.
*   **API Keys (`/dashboard/keys`)**: Manage credentials for AI providers.
*   **Clean Files (`/dashboard/documents`)**: Upload sensitive documents to establish secure RAG knowledge sources.
*   **Playground (`/dashboard/playground`)**: Test your API keys and compression rules in a secure sandbox.

## ⚙️ Installation & Development

The platform is built on **FastAPI**, utilizing **SQLAlchemy** for asynchronous state management and **Jinja2** for a lightning-fast responsive frontend.

### 1. Setup Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file based on the implementation requirements (API Keys, DB URL).

### 3. Run Development Server
```bash
uvicorn main:app --reload
```

Access the dashboard at `http://127.0.0.1:8000/dashboard`.

---
*Firma-KI is optimized for high-performance enterprise AI workloads.*
