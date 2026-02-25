# Firma-KI: Next-Gen AI Gateway & Semantic Compressor

Firma-KI is an enterprise-grade AI proxy gateway, security firewall, and semantic network optimizer designed to intercept, compress, and secure outbound interactions with Large Language Models (LLMs). It dramatically reduces API costs (up to 97%) while ensuring absolute GDPR/PII compliance before any data leaves your infrastructure. 

## 🛡️ The Pure GDPR Shield (Zero-Trust PII Anonymizer)

The Pure GDPR Shield is a deterministic, zero-trust middleware layer designed specifically for the strict data privacy laws of the European Mittelstand (DSGVO). It acts as an absolute semantic firewall between your internal enterprise data and external cloud AI providers. By dynamically sanitizing all outbound API requests, it guarantees that cloud LLMs (like DeepSeek or OpenAI) never process, see, or train on your sensitive corporate information.

### How the Architecture Works (The 3-Step Vault)

1. **Intercept & Mask (Outbound):** When a legacy system or employee sends a prompt, the Firma-KI gateway intercepts it locally. Using lightweight, on-premise NLP and custom Regex patterns, it identifies Personally Identifiable Information (PII) such as Names, Addresses, IBANs, and internal Project Codes. It instantly swaps these with cryptographic, context-aware placeholders (e.g., *Navid Falah* becomes `[PER_01]`; *DE12345...* becomes `[IBAN_01]`).
2. **Sanitized Processing (Cloud):** The cloud LLM receives and processes a completely anonymized prompt. It performs the requested logic, summarization, or translation using the placeholders, entirely blind to the underlying proprietary data.
3. **Re-Injection (Inbound):** When the LLM returns the generated response, the local Firma-KI gateway intercepts the payload, maps the placeholders back to their original values from its secure local memory, and delivers the finalized, readable text to the end-user.

## 🌟 Core Concepts

The Firma-KI engine fundamentally alters the way applications talk to AI models by inserting a 3-Stage NEX Bytecode Pipeline between the user and the final commercial AI model (DeepSeek, OpenAI, Anthropic).

### The NEX Bytecode Pipeline:
1. **Stage 1 (Compressor & PII Filter):** A fast, local/cheap AI model reads the user's bloated prompt. It first scans for and strips all Personally Identifiable Information (PII) such as Names, Emails, IBANs, and internal IDs, replacing them with cryptographic placeholder tokens. It then semantically crushes the prompt into ultra-dense **NEX Bytecode** (e.g. `[FACT:x=y]`, `[CMD:Summarize]`).
2. **Stage 2 (The Middle AI):** The commercial AI (e.g. DeepSeek-Coder, GPT-4) receives the compressed NEX Bytecode. Because the token count is reduced by 60-90%, the commercial AI processes the logic lightning-fast and costs fractions of a cent, returning its answer in the same dense NEX Bytecode format.
3. **Stage 3 (Human Translator):** An expander model intercepts the returning bytecode, unmasks the PII placeholders back into their original real-world values, and translates the dense logic into a beautifully formatted, natural-sounding human response. Structural data like Code and JSON are gracefully passed through natively.

## 🚀 Key Features

*   **Financial Efficiency Tracking:** Live telemetry mapping your token payloads against high-cost commercial baselines (e.g., Claude Opus @ $15/$75 per 1M). Firma-KI visually tracks exactly how many Euros are saved per request by utilizing the NEX proxy infrastructure.
*   **Total Transparency Audit:** A robust dashboard displaying the exact payloads for every stage. You can inspect the "Stage 1 Input", the "Middle AI Payload" (NEX format), and the "Stage 3 Output" alongside dynamic Token-in/Token-out savings ratios.
*   **Two-Way GDPR Masking:** Protects sensitive data dynamically without relying on static Regex. Advanced contextual analysis masks dynamic enterprise IDs before payload export, re-injecting them seamlessly upon the return trip.
*   **Role-Based Sharing & Access:** Easily generate invite links with granular "Editor" or "Viewer" permissions to onboard organizational team members.
*   **File Analysis Hub (RAG):** Upload PDFs, spreadsheets, or raw codebase archives. Firma-KI chunks and embeds documents into a Vector Database to enable rich Retrieval-Augmented Generation (RAG) interactions directly linked to the user's queries.
*   **Secure API Streaming:** Connect entirely separate applications directly to Firma-KI using standard compatible proxy endpoints. Firma-KI streams responses chunk-by-chunk for low-latency frontend integrations.

## 🛠 Usage & Interaction

*   **The Dashboard (`/dashboard/`)**: Review cost metrics, monitor global token burn, and audit security pipeline executions.
*   **Security Audit (`/dashboard/audit/`)**: Review blocked payloads, monitor PII filtration success rates, and configure API-key specific enforcement bounds.
*   **Secure Chat (`/dashboard/chat/`)**: Directly interact with the 3-stage pipeline in an isolated sandbox. Select specific vectorized Knowledge Base entries (uploaded via the File Analysis hub) to ground the AI's logic.
*   **API Key Management (`/accounts/api-keys/`)**: Generate standard `sk-firmaki...` bearer tokens to configure your external applications to point to `/gateway/v1/chat/completions`.

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
