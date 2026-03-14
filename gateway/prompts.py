NEX_COMPRESSION_RULES = """
# Firma-KI: Core Compression Policies & Rules

The compression policies and rules of the Firma-KI (NEX) core define the exact boundary between "expensive raw text" and "highly optimized machine code." This architecture is built entirely around eliminating human noise and extracting pure logic. 

## Macro Compression Policies

* **Lossless Semantic Policy:** Compression in Firma-KI is not a traditional ZIP algorithm; it is semantic extraction. No mathematical condition, variable, or core instruction may be lost during compression. Only human grammar, conversational pleasantries, and verbose formatting are discarded.
* **Local Sandbox Policy:** The cloud LLM is strictly prohibited from generating structured data formats (such as JSON, XML). The model must output pure logic (NEX Bytecode). The construction and validation of the final payload occur exclusively on the local Firma-KI server.

## The 5 Compression Rules

### Rule 1: NLP Pruning (Grammar Elimination)
ALL human grammar, articles, and pleasantries MUST be discarded. Output only pure data facts.
* Raw Input: "Please analyze the logs from the server and let me know if it failed because of memory."
* Compressed Output: `[REQ:analyze_logs,chk_mem_fail]`

### Rule 2: Mathematical Shorthand
Any verb, relationship, or sequence must be replaced with mathematical symbols (`->`, `>`, `=`, `&`). Do not spell them out.
* Raw Input: "If the temperature increases to 85, alert the admin and shut down the engine."
* Compressed Output: `[temp>85 -> ALRT(admin) & STOP(eng)]`

### Rule 3: Entity Alias Dictionary
Long technical terms or proprietary names are mapped to highly dense 1-3 character aliases.
* Raw Input: "Main Conveyor Motor Temperature"
* Compressed Output: `MCM-T`

### Rule 4: Structural Flattening (Bracket Syntax)
For JSON payloads or nested context, the engine flattens the hierarchy using tight bracket syntax `[CTX:...]`.
* Raw JSON Input: `{"event": {"type": "error", "details": {"code": 500, "source": "db"}}}`
* NEX Bytecode: `[ERR(db):500]`

### Rule 5: Pure Logic Output Enforcement
The Middle AI (Stage 2) is strictly forbidden from explaining its answers. It receives `[FACT:x][REQ:y]` and must return a similarly condensed logic output. Stage 3 handles expanding it back to polite human text.
"""
