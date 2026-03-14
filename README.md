# Firma-KI: Next-Gen AI Gateway & Semantic Compressor

Firma-KI is an enterprise-grade AI proxy gateway, security firewall, and semantic network optimizer designed to intercept, compress, and accelerate outbound interactions with Large Language Models (LLMs). It dramatically reduces API costs (up to 97%) by transmuting conversational bloat into highly dense NEX bytecode.

## 🌟 Core Architecture (NEX Pipeline)

The Firma-KI engine fundamentally alters the way applications talk to AI models through a 3-Stage NEX Bytecode Pipeline:

1. **Stage 1 (Compressor):** A fast, local/cheap AI model reads the user's bloated prompt. It semantically crushes the prompt into ultra-dense **NEX Bytecode** (e.g. `[FACT:x=y]`, `[CMD:Summarize]`).
2. **Stage 2 (The Middle AI):** The commercial AI (e.g. DeepSeek-Coder, GPT-4) receives the compressed NEX Bytecode. Because the token count is reduced by 60-90%, the commercial AI processes the logic lightning-fast and costs fractions of a cent, returning its answer in the same dense NEX Bytecode format.
3. **Stage 3 (Human Translator):** An expander model intercepts the returning bytecode, and translates the dense logic back into a beautifully formatted, natural-sounding human response. Structural data like Code and JSON are gracefully passed through natively.

## 🚀 Advanced Gateway Capabilities

*   **Dual-Engine Generative Compression (NLC / CAC):** Operates using lossless semantic extraction. No mathematical condition, variable, or core instruction is lost during compression. Only human grammar, conversational pleasantries, and verbose formatting are discarded.
*   **Confidence-Driven Cascade Routing:** Dynamically routes complex logic requests to heavier models (like GPT-4o) and simpler extractions to lightning-fast models (like DeepSeek) based on real-time task complexity estimation.
*   **Domain-Specific Semantic Caching:** Utilizes Vector Databases/Embeddings to instantly intercept and serve responses to geometrically similar questions without ever hitting external LLM endpoints, reducing latency to near-zero for common enterprise topics.
*   **Edge-Native Processing Nodes:** Manage geographic processing zones for data sovereignty, ensuring computing can be forced to regional sovereign clouds (e.g., German-only datacenters).
*   **Centralized MCP Gateway:** Provides a unified integration point to connect Large Language Models with external Agentic capabilities.
*   **Financial Efficiency Tracking:** Live telemetry mapping your token payloads against high-cost commercial baselines (e.g., Claude Opus @ $15/$75 per 1M). Firma-KI visually tracks exactly how many Euros are saved per request by utilizing the NEX proxy infrastructure.

## 🌐 Future Roadmap: Enterprise Scalability

When scaling Firma-KI for specific regional markets (like the DACH region), several advanced enterprise features are slated for the roadmap:
* **Local AI Hosting & "Sovereign Cloud" Integrations:** Direct support for Aleph Alpha (Luminous) and scripts for hosting the pipeline on Open Telekom Cloud / Hetzner.
* **Advanced BSI-Compliant Logging:** Immutable audit trails, WORM storage exports, and cryptographic signatures for all system decisions.
* **Works Council (Betriebsrat) Compliance Mode:** Advanced anonymization modes to protect employee monitoring and usage data.
* **Liability & Risk Management Scoring:** "Confidence & Risk" badges injected into the outputs to flag hallucinations or unverified claims for high-stakes enterprise usage.
* **Sustainable IT (GreenTech Tracking):** A Carbon Tracking Dashboard highlighting Grams of CO2 saved via NEX token compression architectures vs traditional heavy LLM inferences.

## 🛠 Usage & Interaction

*   **The Dashboard (`/dashboard/`)**: Review cost metrics, monitor global token burn, and audit security pipeline executions.
*   **Security & Policy Audit (`/dashboard/security-audit/`)**: Review logs and metrics for compression operations, and configure key-level security toggles.
*   **MCP Tools (`/dashboard/mcp-tools/`)**: Configure and manage the external tool endpoints allowing autonomous agent execution via the gateway.
*   **Edge Nodes (`/dashboard/edge-nodes/`)**: Register and manage geographic processing zones and routing overrides.
*   **File Analysis Hub (`/dashboard/files/`)**: Upload PDFs, spreadsheets, or raw codebase archives to establish vector-based RAG knowledge sources.

## ⚙️ Installation & Development

The platform is built on fully-asynchronous Django 5.x channels, utilizing Postgres/SQLite state management, and TailwindCSS+Alpine.js for a lightning-fast responsive frontend.

1. Clone repository and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run database migrations:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```
3. Boot the asynchronous development server:
   ```bash
   python manage.py runserver
   ```
