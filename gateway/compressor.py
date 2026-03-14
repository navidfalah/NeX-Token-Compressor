"""
Firma-KI Gateway — NEX Output Deflation Prompt
Retained from the legacy compressor for use by nex_pipeline.py.
The TokenCompressor and PIIMasker classes have been replaced by:
  - gateway.compression.DualEngineCompressor (Dual-Engine Generative Compression Matrix)
  - gateway.pii_masker.PIIMasker (standalone GDPR-compliant PII masker)
"""

# ---------------------------------------------------------------------------
# Rule 5 — Output Deflation System Prompt (appended to every API call)
# ---------------------------------------------------------------------------
NEX_OUTPUT_DEFLATION_PROMPT = """\
OUTPUT FORMAT RULES (MANDATORY):
- Respond ONLY in NEX Bytecode. No prose. No markdown headers.
- Use entity aliases when defined (e.g. MCM-T, SVR-1).
- Boolean logic: use & (AND) | (OR) ! (NOT) instead of keywords.
- Conditions: use RPN stack notation (e.g. `temp 85 > ALRT=1`).
- Lists: use comma-separated inline notation `[a,b,c]`.
- Omit all explanations, pleasantries, and filler text.
- Max response length: minimize aggressively.
"""
