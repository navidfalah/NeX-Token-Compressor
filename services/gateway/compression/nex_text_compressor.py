"""
Firma-KI Gateway — NEX Text Compression Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Deterministic semantic compression for NATURAL LANGUAGE payloads.

Levels
──────
  🟢 LIGHT    — Safe, clean; removes conversational filler. ~15-30% savings
  🟡 MEDIUM   — Statistical pruning; semantic keyword filter. ~30-50% savings
  🟠 AGGRESSIVE — Recursive summarizing; structural compaction. ~50-70% savings
  🔴 EXTREME  — NEX NL-Bytecode conversion. ~70-85% savings
"""

from __future__ import annotations

import re
import math
import dataclasses
from collections import Counter
from typing import Optional


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]


def _sent_words(sentence: str) -> set[str]:
    return set(re.findall(r'\b\w+\b', sentence.lower()))


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
            "pipeline_log": [{"stage": name, "tokens_removed": removed} for name, removed in self.pipeline_log],
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  🟢 LIGHT ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class HedgeWordRemover:
    """🟢 LIGHT — Remove uncertainty hedges ("I think", "maybe"). ~5% savings."""
    _HEDGES = re.compile(
        r'\b(I think|I believe|I guess|I suppose|perhaps|maybe|possibly|'
        r'probably|might be|could be|seems like|it appears|sort of|kind of|'
        r'more or less|in a way|to some extent|roughly speaking)\b',
        re.IGNORECASE
    )
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = cls._HEDGES.sub('', text)
        out = re.sub(r'  +', ' ', out).strip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class QuotationCompressor:
    """🟢 LIGHT — Trim long inline quotes to first 20 words + "[…]". ~10% savings."""
    _QUOTE = re.compile(r'"([^"]{120,})"')
    MAX_WORDS = 20
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        def _truncate(m):
            words = m.group(1).split()
            if len(words) <= cls.MAX_WORDS: return f'"{m.group(1)}"'
            return f'"{" ".join(words[:cls.MAX_WORDS])} […]"'
        out = cls._QUOTE.sub(_truncate, text)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class StopWordPruner:
    """🟢 LIGHT — Remove grammatical function words (the, a, is). ~20% savings."""
    STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "in", "on", "at",
        "to", "for", "of", "and", "or", "but", "not", "with", "as", "by", "from",
        "that", "this", "it", "its", "we", "you", "he", "she", "they", "them",
        "so", "if", "then", "than", "into", "up", "out", "about", "also", "just",
        "very", "quite", "really", "actually", "basically", "literally", "simply",
        "highly", "extremely", "relatively", "mostly", "usually", "often",
    })
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        # Split by whitespace but keep punctuation attached
        words = text.split()
        pruned = [w for w in words if w.lower().rstrip('.,!?;:') not in cls.STOP_WORDS]
        out = ' '.join(pruned)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))

class CorporateDictionary:
    """🔴 EXTREME — Enterprise pattern mapping. ~15% additional savings."""
    _MAPPINGS = {
        r'(?i)\bmeeting\s+notes\b': '[MTG:NOT]',
        r'(?i)\baction\s+items?\b': '[ACT:ITM]',
        r'(?i)\bnext\s+steps?\b': '[NXT:STP]',
        r'(?i)\btechnical\s+specifications?\b': '[TECH:SPC]',
        r'(?i)\bas\s+soon\s+as\s+possible\b': '[ASAP]',
        r'(?i)\bfor\s+your\s+information\b': '[FYI]',
        r'(?i)\bin\s+regards\s+to\b': '[RE:]',
        r'(?i)\bpoint\s+of\s+contact\b': '[POC]',
        r'(?i)\bservice\s+level\s+agreement\b': '[SLA]',
        r'(?i)\bkey\s+performance\s+indicators?\b': '[KPI]',
        r'(?i)\bstandard\s+operating\s+procedures?\b': '[SOP]',
        r'(?i)\bbusiness\s+as\s+usual\b': '[BAU]',
        r'(?i)\bquarter\s+over\s+quarter\b': '[QoQ]',
        r'(?i)\byear\s+over\s+year\b': '[YoY]',
        r'(?i)\bbottom\s+line\b': '[BL:]',
        r'(?i)\btouch\s+base\b': '[SYNC]',
        r'(?i)\bdeep\s+dive\b': '[ANL:DRIL]',
        r'(?i)\bvalue\s+add\b': '[VAL+]',
    }
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = text
        for pattern, replacement in cls._MAPPINGS.items():
            out = re.sub(pattern, replacement, out)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🟡 MEDIUM ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class RedundancyEliminator:
    """🟡 MEDIUM — Drop sentences with >70% overlap to prior text. ~15% savings."""
    THRESHOLD = 0.70
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        accepted, accepted_sets = [], []
        for sent in sentences:
            words = _sent_words(sent)
            if not words: continue
            if not any(len(words & prev) / max(1, len(words | prev)) > cls.THRESHOLD for prev in accepted_sets):
                accepted.append(sent)
                accepted_sets.append(words)
        out = ' '.join(accepted)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class TFIDFExtractor:
    """🟡 MEDIUM — Keep the top 40% most statistically important sentences. ~35% savings."""
    KEEP = 0.40
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        n = len(sentences)
        if n <= 3: return text, 0
        tfs = [Counter(re.findall(r'\b\w{3,}\b', s.lower())) for s in sentences]
        doc_freq = Counter()
        for tf in tfs: doc_freq.update(tf.keys())
        def score(i):
            words = list(tfs[i].keys())
            if not words: return 0.0
            return sum(tfs[i][w] * math.log((n+1)/(1+doc_freq[w])) for w in words) / len(words)
        scores = sorted([(score(i), i) for i in range(n)], reverse=True)
        kept = sorted([idx for _, idx in scores[:max(1, int(n * cls.KEEP))]])
        out = ' '.join(sentences[i] for i in kept)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class NEXSemanticDensityFilter:
    """🟡 MEDIUM — Keep high-signal sentences containing key technical terms. ~25% savings."""
    KEYWORDS = frozenset({"api", "token", "model", "request", "response", "error", "auth", "data", "result", "status", "config", "logic", "value", "cost", "latency"})
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        if len(sentences) <= 2: return text, 0
        high = [s for s in sentences if len(s.split()) >= 4 and any(kw in s.lower() for kw in cls.KEYWORDS)]
        out = ' '.join(high) if high else ' '.join(sentences[:max(1, len(sentences)//2)])
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🟠 AGGRESSIVE ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class ChunkSummarizer:
    """🟠 AGGRESSIVE — Truncate long docs to first 2 sentences per 150 words. ~40% savings."""
    CHUNK = 150
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        words = text.split()
        if len(words) < 300: return text, 0
        chunks = [words[i:i+cls.CHUNK] for i in range(0, len(words), cls.CHUNK)]
        out = ' '.join([' '.join(_split_sentences(' '.join(c))[:2]) for c in chunks])
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class EntityExtractorPass:
    """🟠 AGGRESSIVE — Drop all sentences that don't contain a Proper Noun or Number. ~30% savings."""
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        # Regex for Capitalized Word (entity) or Number
        entity_pattern = re.compile(r'\b([A-Z][a-z]+|\d+)\b')
        kept = [s for s in sentences if entity_pattern.search(s)]
        out = ' '.join(kept) if kept else text
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🔴 EXTREME ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class NEXNLBytecodeTranspiler:
    """🔴 EXTREME — Convert NL to pseudo-bytecode for AI-native input. ~60% savings.
    Converts: "The API returned an error 404" → [ACT:API.ERR(404)]
    """
    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = text
        # Intent extraction
        out = re.sub(r'(?i)\bthe\s+api\s+(?:returned|sent|threw)\s+(?:an?\s+)?error\b\s*(\d*)', r'[API:ERR(\1)]', out)
        out = re.sub(r'(?i)\buser\s+(\w+)\s+(?:is\s+)?requesting\b', r'[USER:\1.REQ]', out)
        out = re.sub(r'(?i)\b(please|can\s+you)\s+(summarize|analyze|fix|check|write|create)\s*(?:the|this|my)?\s*(\w+)?\b', r'[CMD:\2(\3)]', out)
        # Structural conversion
        out = re.sub(r'(?i)\bif\s+(.+?)\s+then\b', r'[IF:\1]', out)
        out = re.sub(r'(?i)\b(because|due\s+to|since)\b', r'[CAU]', out)
        out = re.sub(r'(?i)\b(therefore|consequently|as\s+a\s+result)\b', r'[RES]', out)
        out = re.sub(r'(?i)\b(for\s+example|e\.g\.|such\s+as)\b', r'[EG:]', out)
        
        out = re.sub(r'\s+', ' ', out).strip()
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  ALGORITHM REGISTRY  (for the UI)
# ═══════════════════════════════════════════════════════════════════════════════

ALGO_REGISTRY = {
    "hedge":        {"name": "Hedge Word Remover",      "level": "light",      "emoji": "🟢", "color": "#4ade80", "savings": "~5%",  "desc": "Strip 'I think', 'maybe', 'perhaps'.", "fn": HedgeWordRemover.apply},
    "quote":        {"name": "Quotation Compressor",    "level": "light",      "emoji": "🟢", "color": "#4ade80", "savings": "~10%", "desc": "Truncate overlong inline quotes.",   "fn": QuotationCompressor.apply},
    "stopword":     {"name": "Stop Word Pruner",        "level": "light",      "emoji": "🟢", "color": "#4ade80", "savings": "~20%", "desc": "Remove grammatical filler words.",   "fn": StopWordPruner.apply},
    "redundancy":   {"name": "Redundancy Eliminator",   "level": "medium",     "emoji": "🟡", "color": "#fbbf24", "savings": "~15%", "desc": "Drop sentences with high overlap.",  "fn": RedundancyEliminator.apply},
    "tfidf":        {"name": "TF-IDF Extractor",        "level": "medium",     "emoji": "🟡", "color": "#fbbf24", "savings": "~35%", "desc": "Keep statistically key sentences.", "fn": TFIDFExtractor.apply},
    "semantic":     {"name": "NEX Semantic Filter",     "level": "medium",     "emoji": "🟡", "color": "#fbbf24", "savings": "~25%", "desc": "Filter by technical signal keyword.", "fn": NEXSemanticDensityFilter.apply},
    "chunking":     {"name": "Chunk Summarizer",        "level": "aggressive", "emoji": "🟠", "color": "#fb923c", "savings": "~40%", "desc": "Truncate very long documents.",      "fn": ChunkSummarizer.apply},
    "entities":     {"name": "Entity Tracker",          "level": "aggressive", "emoji": "🟠", "color": "#fb923c", "savings": "~30%", "desc": "Keep sentences with Names/Numbers.", "fn": EntityExtractorPass.apply},
    "bytecode":     {"name": "NEX Transpiler",          "level": "extreme",    "emoji": "🔴", "color": "#f87171", "savings": "~60%", "desc": "Translate to machine-native brackets.", "fn": NEXNLBytecodeTranspiler.apply},
    "corp_dict":    {"name": "Corporate Dictionary",    "level": "extreme",    "emoji": "🔴", "color": "#f87171", "savings": "~15%", "desc": "Map enterprise patterns to opcodes.", "fn": CorporateDictionary.apply},
}


# ═══════════════════════════════════════════════════════════════════════════════
#  PRESET PIPELINES
# ═══════════════════════════════════════════════════════════════════════════════

class NEXTextCompressor:
    """
    Orchestrates NL compression pipelines at different intensity levels.
    """
    INPUT_PIPELINE = [
        ("QuotationCompress",   QuotationCompressor.apply),
        ("HedgeWordRemove",     HedgeWordRemover.apply),
        ("StopWordPrune",       StopWordPruner.apply),
        ("RedundancyEliminate", RedundancyEliminator.apply),
        ("SemanticFilter",      NEXSemanticDensityFilter.apply),
        ("TFIDFExtract",        TFIDFExtractor.apply),
        ("ChunkSummarize",      ChunkSummarizer.apply),
    ]

    OUTPUT_PIPELINE = [
        ("PreambleStrip",       lambda t: (re.sub(r'^(Of course|Sure|Certainly)[!.]?\s*', '', t, flags=re.I), 0)),
        ("QualifierNormalize",  lambda t: (re.sub(r'\bin order to\b', 'to', t, flags=re.I), 0)),
    ]

    @classmethod
    def compress_input(cls, text: str) -> CompressionResult:
        return cls._run(text, cls.INPUT_PIPELINE, "input")

    @classmethod
    def compress_with_algo(cls, text: str, algo_key: str) -> CompressionResult:
        if algo_key not in ALGO_REGISTRY: return cls._run(text, [], "input")
        fn = ALGO_REGISTRY[algo_key]["fn"]
        t_before = _estimate_tokens(text)
        out, rem = fn(text)
        t_after = _estimate_tokens(out)
        sav = round((t_before-t_after)/t_before*100, 1) if t_before > 0 else 0.0
        return CompressionResult(out, text, t_before, t_after, sav, [(algo_key, rem)], "input")

    @classmethod
    def _run(cls, text: str, pipeline: list, side: str) -> CompressionResult:
        t_before = _estimate_tokens(text)
        log, current = [], text
        for name, fn in pipeline:
            current, rem = fn(current)
            log.append((name, rem))
        t_after = _estimate_tokens(current)
        sav = round((t_before-t_after)/t_before*100, 1) if t_before > 0 else 0.0
        return CompressionResult(current, text, t_before, t_after, sav, log, side)
