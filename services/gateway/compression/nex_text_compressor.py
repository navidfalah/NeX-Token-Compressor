"""
Firma-KI Gateway — NEX Text Compression Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This module implements deterministic semantic compression for NATURAL LANGUAGE
payloads following the NEX philosophy: only the semantic content of the text
matters — every filler word, redundant phrase, and syntactically decorative
element can be discarded without losing the meaning the AI model needs to act on.

Architecture
────────────
INPUT SIDE (before sending to AI model):
  Transform verbose human text into a dense, semantically rich payload that
  costs far fewer tokens while preserving 95%+ of actionable information.

  Algorithms:
    - StopWordPruner         : Remove grammatical fillers (the, a, an, …)
    - RedundancyEliminator   : Drop sentences with >70% Jaccard overlap to prior
    - TFIDFExtractor         : Score & keep the top 40% highest-information sentences
    - NEXSemanticDensityFilter: Signal-keyword filter — keep high-signal sentences only
    - ChunkSummarizer        : Structure-preserving truncation of long documents
    - HedgeWordRemover       : Strip uncertainty hedges ("I think", "perhaps", "maybe")
    - QuotationCompressor    : Trim long inline quotes to 20 words + ellipsis

OUTPUT SIDE (after AI model responds, before forwarding to user):
  Clean up the AI response: remove conversational preambles, unnecessary lists
  of caveats, and repeated acknowledgements that add zero value.

  Algorithms:
    - PreambleStripper       : Remove "Of course!", "Certainly! Here's…" openings
    - BulletListDenser       : Collapse verbose multi-line bullets into single lines
    - CaveatReducer          : Remove standard AI disclaimer sentences
    - QualifierNormalizer    : Replace verbose phrases with compact equivalents
    - TrailingAcknowledgement: Remove closing "I hope this helps!" type lines

Usage
─────
    from services.gateway.compression.nex_text_compressor import NEXTextCompressor

    result = NEXTextCompressor.compress_input(long_text)
    result = NEXTextCompressor.compress_output(ai_response_text)

    # result.compressed      — the compressed string
    # result.tokens_before
    # result.tokens_after
    # result.savings_pct
    # result.pipeline_log    — list of (stage_name, tokens_removed)
"""

from __future__ import annotations

import re
import math
import dataclasses
from collections import Counter
from typing import Optional


# ── Shared utilities ───────────────────────────────────────────────────────────

def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]


def _sent_words(sentence: str) -> set[str]:
    return set(re.findall(r'\b\w+\b', sentence.lower()))


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclasses.dataclass
class CompressionResult:
    compressed: str
    original: str
    tokens_before: int
    tokens_after: int
    savings_pct: float
    pipeline_log: list[tuple[str, int]]
    side: str

    def summary(self) -> dict:
        return {
            "side": self.side,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_before - self.tokens_after,
            "savings_pct": self.savings_pct,
            "pipeline_log": [
                {"stage": name, "tokens_removed": removed}
                for name, removed in self.pipeline_log
            ],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT-SIDE ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class StopWordPruner:
    """
    Remove high-frequency grammatical function words that carry zero semantic
    payload for an AI model parsing intent.

    The resulting text is slightly telegraphic ("user request access token"
    instead of "the user is requesting access to the token") — which is
    exactly the machine-native representation NEX targets.
    """
    STOP_WORDS: frozenset[str] = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "in", "on", "at",
        "to", "for", "of", "and", "or", "but", "not", "with", "as", "by",
        "from", "that", "this", "it", "its", "we", "you", "he", "she", "they",
        "them", "their", "there", "here", "so", "if", "then", "than", "into",
        "up", "out", "about", "over", "also", "just", "very", "quite", "now",
    })

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        words = text.split()
        pruned = [
            w for w in words
            if w.lower().rstrip('.,!?;:') not in cls.STOP_WORDS
        ]
        out = ' '.join(pruned)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class RedundancyEliminator:
    """
    Compares every sentence against all previously accepted sentences using
    Jaccard similarity on word sets. Sentences with overlap >70% are dropped —
    they are paraphrases, not new information.
    """
    JACCARD_THRESHOLD: float = 0.70

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        accepted: list[str] = []
        accepted_sets: list[set[str]] = []

        for sent in sentences:
            words = _sent_words(sent)
            if not words:
                continue
            is_duplicate = any(
                len(words & prev) / max(1, len(words | prev)) > cls.JACCARD_THRESHOLD
                for prev in accepted_sets
            )
            if not is_duplicate:
                accepted.append(sent)
                accepted_sets.append(words)

        out = ' '.join(accepted)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class TFIDFExtractor:
    """
    Scores each sentence by TF-IDF (term frequency × inverse document frequency)
    across the document's sentence corpus, then keeps the top 40% of sentences
    ranked by score. Re-orders by original position to preserve coherence.
    """
    KEEP_FRACTION: float = 0.40

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        n = len(sentences)
        if n <= 3:
            return text, 0

        STOP = StopWordPruner.STOP_WORDS

        def tokenize(s: str) -> list[str]:
            return [w.lower() for w in re.findall(r'\b\w{3,}\b', s) if w.lower() not in STOP]

        tfs: list[Counter] = [Counter(tokenize(s)) for s in sentences]
        all_words = [w for tf in tfs for w in tf]
        doc_freq: Counter = Counter()
        for tf in tfs:
            doc_freq.update(tf.keys())

        def idf(word: str) -> float:
            return math.log((n + 1) / (1 + doc_freq.get(word, 0)))

        def score_sentence(i: int) -> float:
            words = tokenize(sentences[i])
            if not words:
                return 0.0
            return sum(tfs[i][w] * idf(w) for w in words) / len(words)

        scores = [(score_sentence(i), i) for i in range(n)]
        scores.sort(reverse=True)
        keep_n = max(1, int(n * cls.KEEP_FRACTION))
        kept_indices = sorted(idx for _, idx in scores[:keep_n])
        out = ' '.join(sentences[i] for i in kept_indices)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class NEXSemanticDensityFilter:
    """
    NEX S1 Algorithm: Signal-keyword semantic density filter.

    A sentence is "high signal" if it contains domain-relevant keywords
    that indicate concrete information (results, actions, values, decisions).
    Low-signal filler sentences are dropped.

    This is the fastest algorithm in the pipeline — O(n) word scan.
    """
    SIGNAL_KEYWORDS: frozenset[str] = frozenset({
        # Technical / system concepts
        "api", "token", "model", "request", "response", "error", "status",
        "endpoint", "auth", "key", "data", "payload", "schema", "config",
        "module", "function", "class", "method", "parameter", "variable",
        "algorithm", "compression", "pipeline", "route", "cascade", "tier",
        # Outcome-indicating words
        "result", "output", "return", "value", "cost", "latency", "metric",
        "performance", "rate", "limit", "threshold", "count", "total",
        "increase", "decrease", "fail", "success", "error", "warning",
        "found", "detected", "triggered", "enabled", "disabled",
        # Analytical words
        "analysis", "study", "evidence", "shows", "demonstrates", "indicates",
        "conclude", "because", "therefore", "cause", "effect", "impact",
        "measure", "evaluate", "compare", "optimize",
    })

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        if len(sentences) <= 2:
            return text, 0

        high_signal = [
            s for s in sentences
            if len(s.split()) >= 4 and
            any(kw in s.lower() for kw in cls.SIGNAL_KEYWORDS)
        ]

        # Never delete everything — fall back to first half if nothing passes
        if not high_signal:
            high_signal = sentences[:max(1, len(sentences) // 2)]

        out = ' '.join(high_signal)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class ChunkSummarizer:
    """
    For very long documents: splits into 150-word blocks and retains only the
    first 2 sentences of each block. Structure-preserving & predictable.
    Activates only for texts longer than THRESHOLD words.
    """
    THRESHOLD: int = 500     # words before chunking activates
    CHUNK_SIZE: int = 150    # words per chunk
    SENTENCES_PER_CHUNK: int = 2

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        words = text.split()
        if len(words) < cls.THRESHOLD:
            return text, 0
        chunks = [
            words[i: i + cls.CHUNK_SIZE]
            for i in range(0, len(words), cls.CHUNK_SIZE)
        ]
        result_parts: list[str] = []
        for chunk in chunks:
            chunk_text = ' '.join(chunk)
            sents = _split_sentences(chunk_text)
            result_parts.append(' '.join(sents[:cls.SENTENCES_PER_CHUNK]))
        out = ' '.join(result_parts)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class HedgeWordRemover:
    """
    Remove uncertainty hedges that humans add to soften statements but that
    provide zero additional information to an AI model:
    "I think", "I believe", "perhaps", "maybe", "probably", "sort of", etc.
    """
    _HEDGES = re.compile(
        r'\b(I think|I believe|I guess|I suppose|perhaps|maybe|possibly|'
        r'probably|might be|could be|seems like|it appears|sort of|kind of|'
        r'more or less|in a way|to some extent|roughly speaking|'
        r'if I\'m not mistaken|as far as I know|to my knowledge)\b',
        re.IGNORECASE
    )
    _CLEANUP = re.compile(r'  +')

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = cls._HEDGES.sub('', text)
        out = cls._CLEANUP.sub(' ', out).strip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class QuotationCompressor:
    """
    When users paste long inline quotes (text wrapped in " "), compress them
    to the first 20 words + "[…]". Full quotes increase token count without
    adding new information when the context around them already exists.
    """
    _QUOTE = re.compile(r'"([^"]{80,})"')  # only compress quotes >80 chars
    MAX_WORDS = 20

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        def _truncate(match: re.Match) -> str:
            inner = match.group(1)
            words = inner.split()
            if len(words) <= cls.MAX_WORDS:
                return f'"{inner}"'
            return f'"{" ".join(words[:cls.MAX_WORDS])} […]"'

        out = cls._QUOTE.sub(_truncate, text)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  OUTPUT-SIDE ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class PreambleStripper:
    """
    AI responses frequently open with empty acknowledgements:
    "Of course!", "Sure! Here's what you need:", "Great question!"
    These are stripped — the downstream consumer only needs the content.
    """
    _PREAMBLE = re.compile(
        r'^(Of course[!.]?|Sure[!.]?|Certainly[!.]?|Absolutely[!.]?|'
        r'Great(?: question)?[!.]?|Happy to help[!.]?|No problem[!.]?|'
        r'I\'d be happy to[^.!?]*[.!?]|'
        r'Here(?:\'s| is) (?:what you need|the answer|a|an|the)[^.!?]*[.!?]|'
        r'Let me (?:explain|help|walk you through)[^.!?]*[.!?])\s*',
        re.IGNORECASE | re.MULTILINE
    )

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = cls._PREAMBLE.sub('', text).lstrip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class CaveatReducer:
    """
    Remove boilerplate AI safety and disclaimer sentences:
    "Note that this may vary depending on...", "Please consult a professional..."
    These sentences are heuristically identified by their opening patterns.
    """
    _CAVEAT_PATTERNS = [
        re.compile(r'(?:^|\. )(?:Please note|Note that|Keep in mind|Be aware|'
                   r'It is worth noting|It\'s important to note|'
                   r'Disclaimer:|Please consult|Always consult|'
                   r'This is not (?:legal|medical|financial) advice)[^.!?]*[.!?]',
                   re.IGNORECASE | re.MULTILINE),
    ]

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = text
        for pattern in cls._CAVEAT_PATTERNS:
            out = pattern.sub('', out)
        out = re.sub(r'  +', ' ', out).strip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class QualifierNormalizer:
    """
    Replace verbose AI-preferred phrasings with compact equivalents:
    "in order to" → "to"
    "as a matter of fact" → "in fact"
    "at this point in time" → "now"
    etc.
    """
    _REPLACEMENTS: list[tuple[re.Pattern, str]] = [
        (re.compile(r'\bin order to\b', re.I), 'to'),
        (re.compile(r'\bdue to the fact that\b', re.I), 'because'),
        (re.compile(r'\bat this point in time\b', re.I), 'now'),
        (re.compile(r'\bas a matter of fact\b', re.I), 'in fact'),
        (re.compile(r'\bfor the purpose of\b', re.I), 'for'),
        (re.compile(r'\bin the event that\b', re.I), 'if'),
        (re.compile(r'\bprior to\b', re.I), 'before'),
        (re.compile(r'\bsubsequent to\b', re.I), 'after'),
        (re.compile(r'\ba large number of\b', re.I), 'many'),
        (re.compile(r'\bthe majority of\b', re.I), 'most'),
        (re.compile(r'\bin the near future\b', re.I), 'soon'),
        (re.compile(r'\bin close proximity to\b', re.I), 'near'),
        (re.compile(r'\bhas the ability to\b', re.I), 'can'),
        (re.compile(r'\bis able to\b', re.I), 'can'),
        (re.compile(r'\bit is important to note that\b', re.I), ''),
        (re.compile(r'\bit should be noted that\b', re.I), ''),
    ]

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = text
        for pattern, replacement in cls._REPLACEMENTS:
            out = pattern.sub(replacement, out)
        out = re.sub(r'  +', ' ', out).strip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class TrailingAcknowledgementRemover:
    """
    Remove the last sentence if it's a closing pleasantry:
    "I hope this helps!", "Feel free to ask if you have more questions!", etc.
    """
    _CLOSING = re.compile(
        r'(?:^|\n|\. )(?:I hope (?:this helps|that helps|this was helpful)[!.]?|'
        r'Feel free to (?:ask|reach out)[^.!?\n]*[.!?]|'
        r'Let me know if (?:you have|there\'s)[^.!?\n]*[.!?]|'
        r'If you (?:have|need) (?:any|more|further)[^.!?\n]*[.!?]|'
        r'Don\'t hesitate to [^.!?\n]*[.!?])$',
        re.IGNORECASE | re.MULTILINE
    )

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = cls._CLOSING.sub('', text).strip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class BulletListDenser:
    """
    AI responses often produce multi-line bullet points where each bullet
    has a bold key + a sentence of elaboration. This compressor collapses
    each bullet to just the key + inline summary (max 12 words).
    """
    _BULLET = re.compile(r'^(\s*[-*•]\s*)(\*{0,2})([^:\n]{1,60})(\*{0,2}):\s+(.+)$', re.MULTILINE)
    MAX_SUMMARY_WORDS = 12

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        def _condense(m: re.Match) -> str:
            prefix, bold_open, key, bold_close, rest = m.groups()
            words = rest.split()
            summary = ' '.join(words[:cls.MAX_SUMMARY_WORDS])
            if len(words) > cls.MAX_SUMMARY_WORDS:
                summary += '…'
            return f'{prefix}{bold_open}{key}{bold_close}: {summary}'
        out = cls._BULLET.sub(_condense, text)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class NEXTextCompressor:
    """
    Orchestrates the full INPUT and OUTPUT NEX NL compression pipelines.

    INPUT pipeline (applied before sending to AI):
        1. QuotationCompressor         (trim overlong inline quotes)
        2. HedgeWordRemover            (strip uncertainty hedges)
        3. StopWordPruner              (remove grammatical fillers)
        4. RedundancyEliminator        (drop near-duplicate sentences)
        5. NEXSemanticDensityFilter    (keyword-based high-signal filter)
        6. TFIDFExtractor              (statistical importance ranking)
        7. ChunkSummarizer             (truncate very long docs)

    OUTPUT pipeline (applied to AI response before forwarding):
        1. PreambleStripper            (remove "Of course!" openings)
        2. CaveatReducer               (remove disclaimers)
        3. QualifierNormalizer         (replace verbose phrases)
        4. BulletListDenser            (condense verbose bullet points)
        5. TrailingAcknowledgementRemover (remove "I hope this helps!")
    """

    INPUT_PIPELINE = [
        ("QuotationCompress",       QuotationCompressor.apply),
        ("HedgeWordRemove",         HedgeWordRemover.apply),
        ("StopWordPrune",           StopWordPruner.apply),
        ("RedundancyEliminate",     RedundancyEliminator.apply),
        ("NEXSemanticDensityFilter", NEXSemanticDensityFilter.apply),
        ("TFIDFExtract",            TFIDFExtractor.apply),
        ("ChunkSummarize",          ChunkSummarizer.apply),
    ]

    OUTPUT_PIPELINE = [
        ("PreambleStrip",               PreambleStripper.apply),
        ("CaveatReduce",                CaveatReducer.apply),
        ("QualifierNormalize",          QualifierNormalizer.apply),
        ("BulletListDense",             BulletListDenser.apply),
        ("TrailingAcknowledgeRemove",   TrailingAcknowledgementRemover.apply),
    ]

    @classmethod
    def compress_input(cls, text: str) -> CompressionResult:
        """Apply the full INPUT compression pipeline to natural language text."""
        return cls._run(text, cls.INPUT_PIPELINE, "input")

    @classmethod
    def compress_output(cls, text: str) -> CompressionResult:
        """Apply the full OUTPUT compression pipeline to AI-generated text."""
        return cls._run(text, cls.OUTPUT_PIPELINE, "output")

    @classmethod
    def _run(cls, text: str, pipeline: list, side: str) -> CompressionResult:
        tokens_before = _estimate_tokens(text)
        log: list[tuple[str, int]] = []
        current = text
        for stage_name, fn in pipeline:
            current, removed = fn(current)
            log.append((stage_name, removed))
        tokens_after = _estimate_tokens(current)
        savings_pct = round(
            (tokens_before - tokens_after) / tokens_before * 100, 1
        ) if tokens_before > 0 else 0.0
        return CompressionResult(
            compressed=current,
            original=text,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            savings_pct=savings_pct,
            pipeline_log=log,
            side=side,
        )
