"""
Firma-KI Gateway — Token Compressor
Full NEX Bytecode Compiler implementing all 5 rules from COMPRESSION_RULES.md.

Rule 1: NLP Pruning (Grammar & Stop-words) — 20-30% input token reduction
Rule 2: Entity Tokenization (Alias Mapping) — prevent multi-token waste on repeated terms
Rule 3: Language Normalization (English Shorthand) — exploit tokenizer biases
Rule 4: Stack-Based Logic Translation (RPN) — replace JSON logic with math operators
Rule 5: Output Deflation Enforcement — hidden System Prompt caps output verbosity
"""
import re
import json


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


class TokenCompressor:
    """
    Full NEX Bytecode Compiler.
    Implements all 5 compression rules from COMPRESSION_RULES.md.
    """

    # -----------------------------------------------------------------------
    # Rule 1 — NLP Pruning: English stop-words & filler phrases
    # These are stripped before the prompt is tokenized.
    # -----------------------------------------------------------------------
    FILLER_PHRASES = [
        r'\bplease\b[\s,]*',
        r'\bcould you\b[\s,]*',
        r'\bwould you\b[\s,]*',
        r'\bcan you\b[\s,]*',
        r'\bfeel free to\b[\s]*',
        r'\blet me know\b[\s,]*(?:if[^.]*)?',
        r'\bthank(?:s| you)[^.]*?\.',
        r'\bI hope this (?:helps|answer)[^.]*?\.',
        r'\bof course\b[\s,]*',
        r'\bcertainly\b[\s,]*',
        r'\babsolutely\b[\s,]*',
        r'\bsure[,!\s]+',
        r'\bI(?:\'d| would) be happy to\b[\s,]*',
        r'\bAs an AI\b[^.]*?\.',
        r'\bIt(?:\'s| is) important to (?:note|mention) that\b[\s,]*',
        r'\bin order to\b',          # → "to"
        r'\bdue to the fact that\b',  # → "because"
        r'\bat this point in time\b', # → "now"
        r'\bfor the purpose of\b',    # → "for"
        r'\bin the event that\b',     # → "if"
    ]

    # Simple replacements: verbose → terse
    SHORTHAND_REPLACEMENTS = [
        (r'\bin order to\b',          'to'),
        (r'\bdue to the fact that\b', 'because'),
        (r'\bat this point in time\b','now'),
        (r'\bfor the purpose of\b',   'for'),
        (r'\bin the event that\b',    'if'),
        (r'\bwith regard to\b',       're:'),
        (r'\bwith respect to\b',      're:'),
        (r'\ba number of\b',          'several'),
        (r'\bthe majority of\b',      'most'),
        (r'\bit is possible that\b',  'maybe'),
        (r'\bprovide assistance\b',   'help'),
        (r'\bperform an analysis\b',  'analyze'),
        (r'\bconduct a review\b',     'review'),
        (r'\bmake use of\b',          'use'),
        (r'\binitialize\b',           'init'),
        (r'\bterminate\b',            'end'),
        (r'\bexecute\b',              'run'),
        (r'\bgenerate\b',             'gen'),
        (r'\bparameter\b',            'param'),
        (r'\bvariable\b',             'var'),
        (r'\bfunction\b',             'fn'),
        (r'\breturn\b',               'ret'),
        (r'\bimport\b',               'imp'),
        (r'\bclass\b',                'cls'),
        (r'\basync\b',                'asc'),
        (r'\bawait\b',                'awt'),
        (r'\bprint\b',                'prn'),
        (r'\bconsole\.log\b',         'log'),
        (r'\bmaximum\b',              'max'),
        (r'\bminimum\b',              'min'),
        (r'\bdatabase\b',             'db'),
        (r'\brepository\b',           'repo'),
        (r'\bapplication\b',          'app'),
        (r'\bconfiguration\b',        'cfg'),
        (r'\bauthentication\b',       'auth'),
        (r'\bauthorization\b',        'authz'),
        (r'\btemperature\b',          'temp'),
        (r'\bpressure\b',             'pres'),
    ]

    def __init__(self, compression_rules=None):
        """
        Args:
            compression_rules: QuerySet or list of CompressionRule instances.
        """
        self.custom_rules = compression_rules or []

    # -----------------------------------------------------------------------
    # Rule 2 — Entity Tokenization: Auto-acronym mapping
    # -----------------------------------------------------------------------
    def _build_entity_aliases(self, text):
        """
        Scan for repeated multi-word capitalized phrases and alias them.
        e.g. "Main Conveyor Motor Temperature" (4 tokens) → MCM-T (1 token)
        Returns (text_with_aliases, alias_map).
        """
        alias_map = {}
        # Find all Title Case multi-word phrases (2+ words, each capitalized)
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,4})\b'
        matches = {}
        for m in re.finditer(pattern, text):
            phrase = m.group(1)
            matches[phrase] = matches.get(phrase, 0) + 1

        # Only alias phrases that appear 2+ times (worthwhile)
        for phrase, count in matches.items():
            if count >= 2 and phrase not in alias_map.values():
                # Build acronym from first letters + last part after dash join
                words = phrase.split()
                acronym = ''.join(w[0] for w in words[:-1]).upper()
                suffix = '-' + words[-1][0].upper() if len(words) > 1 else ''
                alias = f"{acronym}{suffix}"
                # Avoid collision
                if alias not in alias_map:
                    alias_map[phrase] = alias

        result = text
        for phrase, alias in alias_map.items():
            result = result.replace(phrase, alias)

        return result, alias_map

    # -----------------------------------------------------------------------
    # Rule 4 — RPN Logic Translation: JSON conditions → math operators
    # -----------------------------------------------------------------------
    def _json_to_rpn(self, text):
        """
        Detect JSON-like logical structures and convert to RPN notation.
        {"operator": "AND", ...} → &
        {"operator": "OR", ...}  → |
        """
        # Replace JSON boolean logic operators
        text = re.sub(r'"operator"\s*:\s*"AND"', '&', text)
        text = re.sub(r'"operator"\s*:\s*"OR"',  '|', text)
        text = re.sub(r'"operator"\s*:\s*"NOT"', '!', text)
        text = re.sub(r'\bAND\b', '&', text)
        text = re.sub(r'\bOR\b',  '|', text)
        text = re.sub(r'\bNOT\b', '!', text)
        # Strip JSON structural punctuation from simple condition objects
        # e.g. {"var": "temp", "op": ">", "val": 85} → temp 85 >
        def simplify_condition(m):
            inner = m.group(1)
            var = re.search(r'"var"\s*:\s*"([^"]+)"', inner)
            op  = re.search(r'"op"\s*:\s*"([^"]+)"', inner)
            val = re.search(r'"val"\s*:\s*([^\s,}]+)', inner)
            if var and op and val:
                return f"{var.group(1)} {val.group(1)} {op.group(1)}"
            return m.group(0)
        text = re.sub(r'\{([^{}]*"var"[^{}]*)\}', simplify_condition, text)
        return text

    def compress(self, text):
        """
        Apply all NEX compression rules to text.
        Returns (compressed_text, original_token_count, compressed_token_count).
        """
        original_token_count = self._estimate_tokens(text)
        compressed = text

        # --- Apply custom organization rules first ---
        for rule in self.custom_rules:
            if hasattr(rule, 'pattern') and hasattr(rule, 'replacement'):
                if rule.is_active:
                    try:
                        compressed = re.sub(
                            re.escape(rule.pattern),
                            rule.replacement,
                            compressed,
                            flags=re.IGNORECASE,
                        )
                    except re.error:
                        continue

        # --- Rule 1: NLP Pruning — strip filler phrases ---
        for pattern in self.FILLER_PHRASES:
            try:
                compressed = re.sub(pattern, ' ', compressed, flags=re.IGNORECASE)
            except re.error:
                continue

        # --- Rule 1: Shorthand replacements ---
        for pattern, replacement in self.SHORTHAND_REPLACEMENTS:
            try:
                compressed = re.sub(pattern, replacement, compressed, flags=re.IGNORECASE)
            except re.error:
                continue

        # --- Rule 2: Entity Tokenization ---
        compressed, _alias_map = self._build_entity_aliases(compressed)

        # --- Rule 4: RPN Logic Translation ---
        compressed = self._json_to_rpn(compressed)

        # --- Cleanup: collapse multiple spaces ---
        compressed = re.sub(r'\s+', ' ', compressed).strip()

        compressed_token_count = self._estimate_tokens(compressed)
        return compressed, original_token_count, compressed_token_count

    def compress_messages(self, messages):
        """
        Compress a list of OpenAI-format messages.
        Returns (compressed_messages, original_tokens, compressed_tokens).
        """
        total_original = 0
        total_compressed = 0
        compressed_messages = []

        for msg in messages:
            if 'content' in msg and msg['content']:
                # Don't compress system prompts that are already NEX instructions
                if msg.get('role') == 'system' and 'NEX Bytecode' in msg['content']:
                    compressed_messages.append(msg)
                    est = self._estimate_tokens(msg['content'])
                    total_original += est
                    total_compressed += est
                    continue

                compressed_content, orig, comp = self.compress(msg['content'])
                total_original += orig
                total_compressed += comp
                compressed_messages.append({
                    **msg,
                    'content': compressed_content,
                })
            else:
                compressed_messages.append(msg)

        return compressed_messages, total_original, total_compressed

    def get_output_deflation_prompt(self):
        """Return the Rule 5 output deflation system prompt snippet."""
        return NEX_OUTPUT_DEFLATION_PROMPT

    @staticmethod
    def _estimate_tokens(text):
        """
        Rough token estimation (1 token ≈ 4 characters for English text).
        """
        if not text:
            return 0
        return max(1, len(text) // 4)


class PIIMasker:
    """
    Handles two-way PII masking for text streams.
    Replaces sensitive data with placeholder tags, and unmasks them later.
    """

    # Basic PII regex patterns.
    PII_PATTERNS = {
        'EMAIL': r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
        'PHONE': r'\b(?:\+?1[-.●]?)?\(?([0-9]{3})\)?[-.●]?([0-9]{3})[-.●]?([0-9]{4})\b'
    }

    def __init__(self):
        self.mask_map = {}
        self.counters = {key: 1 for key in self.PII_PATTERNS.keys()}

    def mask(self, text):
        """
        Scans text for PII patterns, replaces them with tags, and stores the mapping.
        """
        masked_text = text
        for pii_type, pattern in self.PII_PATTERNS.items():
            def replace_match(match):
                original_value = match.group(0)
                # Check if we already have this value in the map
                existing_tag = next((tag for tag, val in self.mask_map.items() if val == original_value), None)
                if existing_tag:
                    return existing_tag

                tag = f"[{pii_type}_{self.counters[pii_type]}]"
                self.mask_map[tag] = original_value
                self.counters[pii_type] += 1
                return tag

            masked_text = re.sub(pattern, replace_match, masked_text)

        return masked_text

    def unmask(self, text):
        """
        Replaces tags back with their original values.
        """
        unmasked = text
        for tag, original_value in self.mask_map.items():
            unmasked = unmasked.replace(tag, original_value)
        return unmasked

    def mask_messages(self, messages):
        """
        Applies masking to a list of OpenAI-format messages.
        """
        masked_messages = []
        for msg in messages:
            if 'content' in msg and msg['content']:
                masked_content = self.mask(msg['content'])
                masked_messages.append({
                    **msg,
                    'content': masked_content,
                })
            else:
                masked_messages.append(msg)

        return masked_messages, list(self.mask_map.keys())
