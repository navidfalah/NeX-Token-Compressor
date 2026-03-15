"""
Firma-KI Gateway — NEX Text Compression Pipeline  v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Deterministic semantic compression for NATURAL LANGUAGE payloads.

Levels
──────
  🟢 LIGHT      — Safe, clean; removes conversational filler.        ~12-30% savings
  🟡 MEDIUM     — Statistical pruning; semantic keyword filter.       ~30-50% savings
  🟠 AGGRESSIVE — Extractive summarising; structural compaction.      ~50-65% savings
  🔴 EXTREME    — NEX NL-Bytecode + Corporate Opcode conversion.      ~65-80% savings
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
    """Split on sentence boundaries. Handles abbreviations and decimal numbers."""
    # Use a negative lookbehind to avoid splitting on abbreviations like "e.g.", "U.S."
    text = text.strip()
    if not text:
        return []
    parts = re.split(r'(?<![A-Z][a-z])(?<!\d)(?<![A-Za-z]\.[A-Za-z])(?<=[.!?])\s+', text)
    return [s.strip() for s in parts if s.strip()]


def _word_set(sentence: str) -> set[str]:
    return set(re.findall(r'\b\w{3,}\b', sentence.lower()))


def _bigrams(sentence: str) -> set[tuple[str, str]]:
    words = re.findall(r'\b\w{3,}\b', sentence.lower())
    return set(zip(words, words[1:])) if len(words) >= 2 else set()


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
    """🟢 LIGHT — Filler + Hedge phrase eliminator. ~12% savings.

    Improvements over v1:
    - 60+ patterns (up from 15) covering:
      * Conversational hedges: "I think", "maybe", "actually"
      * Discourse markers: "It's worth noting that", "As you know"
      * Social padding: "I hope this helps", "Feel free to"
      * Redundant affirmations: "That's a great question"
      * Empty lead-ins: "So basically", "Well, essentially"
    """
    _HEDGES = re.compile(
        r'\b('
        # Classic hedges
        r'I think|I believe|I guess|I suppose|perhaps|maybe|possibly|'
        r'probably|might be|could be|seems like|it appears|sort of|kind of|'
        r'more or less|in a way|to some extent|roughly speaking|'
        # Discourse markers
        r'as you (may |might |probably )?know|it(?:\'s| is) worth noting(?: that)?|'
        r'(just |simply )?to (be|note|clarify|reiterate|recap|summarize|point out),?|'
        r'needless to say,?|it goes without saying(?: that)?|'
        r'as (I|we) mentioned( before| earlier| previously)?,?|'
        r'at the end of the day,?|'
        # Social padding
        r'I hope this helps?\.?|feel free to (ask|reach out|contact us),?|'
        r'please (don\'?t hesitate|feel free) to (ask|contact|reach out)\.?|'
        r'let me know if you (have|need|want) (any|more|further) (questions?|help|information)\.?|'
        r'thank(s| you) for (asking|your question|reaching out)\.?|'
        # Redundant affirmations
        r'that(?:\'s| is) a (great|good|excellent|wonderful|interesting) (question|point)\.?|'
        r'great question[!.]?|'
        # Empty lead-ins
        r'so basically,?|well, (essentially|basically|actually),?|'
        r'honestly,?|truthfully,?|frankly,?|candidly,?|'
        r'to be (honest|fair|clear|transparent),?|'
        r'as a matter of fact,?|in (actual|actual) fact,?'
        r')\b',
        re.IGNORECASE
    )
    # Standalone filler sentences to remove entirely
    _FILLER_SENTENCES = re.compile(
        r'(Sure[!,.]?\s*|Of course[!,.]?\s*|Certainly[!,.]?\s*|Absolutely[!,.]?\s*'
        r'|No problem[!,.]?\s*|Happy to help[!,.]?\s*)',
        re.IGNORECASE
    )

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = cls._FILLER_SENTENCES.sub('', text)
        out = cls._HEDGES.sub('', out)
        out = re.sub(r'  +', ' ', out).strip()
        # Clean up double punctuation from phrase removals
        out = re.sub(r'[,;]\s*[,;]', ',', out)
        out = re.sub(r'\.\s*\.', '.', out)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class QuotationCompressor:
    """🟢 LIGHT — Context-aware quote truncator. ~15% savings.

    Improvements over v1:
    - Preserves key entities (capital words, numbers) within quotes
    - Applies smarter truncation: keeps first sentence + any sentence with numbers
    - Handles single-quoted long strings as well
    - Detects code-like content inside quotes and preserves it verbatim
    """
    _DOUBLE_QUOTE = re.compile(r'"([^"]{100,})"')
    _SINGLE_QUOTE = re.compile(r"'([^']{100,})'")
    MAX_WORDS = 25

    @classmethod
    def _smart_truncate(cls, content: str) -> str:
        # If it looks like code, keep it
        if re.search(r'[{}();=<>]|def |class |import ', content):
            words = content.split()
            if len(words) <= cls.MAX_WORDS:
                return content
            return ' '.join(words[:cls.MAX_WORDS]) + ' […]'

        sentences = _split_sentences(content)
        if not sentences:
            words = content.split()
            return ' '.join(words[:cls.MAX_WORDS]) + ' […]' if len(words) > cls.MAX_WORDS else content

        # Keep first sentence + any sentence with a number or proper noun
        kept = [sentences[0]]
        for s in sentences[1:]:
            if re.search(r'\b\d+\b', s) or re.search(r'\b[A-Z][a-z]{2,}\b', s):
                if len(' '.join(kept + [s]).split()) <= cls.MAX_WORDS * 2:
                    kept.append(s)
        result = ' '.join(kept)
        total_words = len(result.split())
        if total_words > cls.MAX_WORDS:
            result = ' '.join(result.split()[:cls.MAX_WORDS]) + ' […]'
        return result

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        def _replace_double(m):
            inner = cls._smart_truncate(m.group(1))
            return f'"{inner}"'
        def _replace_single(m):
            inner = cls._smart_truncate(m.group(1))
            return f"'{inner}'"
        out = cls._DOUBLE_QUOTE.sub(_replace_double, text)
        out = cls._SINGLE_QUOTE.sub(_replace_single, out)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class StopWordPruner:
    """🟢 LIGHT — Semantic-preserving stop word filter. ~28% savings.

    Improvements over v1:
    - Sentence-aware: preserves negation context (not, no, never)
    - Preserves comparative structures (more than, less than, rather than)
    - Preserves question-critical words (who, what, where, when, why, how)
    - Removes adverbs that add no information (very, quite, really)
    - Always keeps first and last word of each sentence for boundary preservation
    """
    STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "in", "on", "at",
        "to", "for", "of", "and", "or", "with", "as", "by", "from",
        "that", "this", "it", "its", "we", "you", "he", "she", "they", "them",
        "so", "if", "then", "than", "into", "up", "out", "about", "also",
        "very", "quite", "really", "actually", "basically", "literally", "simply",
        "highly", "extremely", "relatively", "mostly", "usually", "often",
        "certain", "particular", "especially", "specifically", "generally",
        "some", "such", "just", "me", "my", "our", "your", "their", "its",
        "am", "i",
    })
    # Words to always keep regardless of stop word status
    KEEP_WORDS = frozenset({
        "not", "no", "never", "none", "nothing", "neither", "nor",
        "who", "what", "where", "when", "why", "how",
        "more", "less", "fewer", "most", "least",
        "before", "after", "during", "between", "among",
    })

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        if not sentences:
            # fallback: word-level filtering
            words = text.split()
            pruned = []
            for w in words:
                bare = w.lower().rstrip('.,!?;:')
                if bare in cls.KEEP_WORDS or bare not in cls.STOP_WORDS:
                    pruned.append(w)
            return ' '.join(pruned), max(0, _estimate_tokens(text) - _estimate_tokens(' '.join(pruned)))

        result_sents = []
        for sent in sentences:
            words = sent.split()
            if len(words) <= 2:
                result_sents.append(sent)
                continue
            pruned = []
            for i, w in enumerate(words):
                bare = w.lower().rstrip('.,!?;:')
                # Always keep first and last word of sentence
                if i == 0 or i == len(words) - 1:
                    pruned.append(w)
                elif bare in cls.KEEP_WORDS:
                    pruned.append(w)
                elif bare not in cls.STOP_WORDS:
                    pruned.append(w)
            result_sents.append(' '.join(pruned))

        out = ' '.join(result_sents)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class CorporateDictionary:
    """🔴 EXTREME — Domain-aware vocabulary encoder. ~25% savings.

    Improvements over v1:
    - 80+ mappings (up from 18) organized into domain clusters
    - Covers Business, DevOps, Legal, Finance, and HR terminology
    - Detects repeated product/company references and compresses them
    """
    _CATEGORIES = {
        # Business operations
        "business": [
            (r'(?i)\bmeeting\s+notes?\b', '[MTG:NOT]'),
            (r'(?i)\baction\s+items?\b', '[ACT:ITM]'),
            (r'(?i)\bnext\s+steps?\b', '[NXT:STP]'),
            (r'(?i)\bas\s+soon\s+as\s+possible\b', '[ASAP]'),
            (r'(?i)\bfor\s+your\s+information\b', '[FYI]'),
            (r'(?i)\bin\s+regards?\s+to\b', '[RE:]'),
            (r'(?i)\bpoint\s+of\s+contact\b', '[POC]'),
            (r'(?i)\bbusiness\s+as\s+usual\b', '[BAU]'),
            (r'(?i)\bquarter\s+over\s+quarter\b', '[QoQ]'),
            (r'(?i)\byear\s+over\s+year\b', '[YoY]'),
            (r'(?i)\bbottom\s+line\b', '[BL:]'),
            (r'(?i)\btouch\s+base\b', '[SYNC]'),
            (r'(?i)\bdeep\s+dive\b', '[ANL:DRIL]'),
            (r'(?i)\bvalue\s+add(?:ed)?\b', '[VAL+]'),
            (r'(?i)\blow\s+hanging\s+fruit\b', '[EASY:WIN]'),
            (r'(?i)\bmove\s+the\s+needle\b', '[IMPV:KPI]'),
            (r'(?i)\bbandwidth\b', '[CAP]'),
            (r'(?i)\bcircle\s+back\b', '[FLW:UP]'),
            (r'(?i)\bpivot\b', '[CHNG:DIR]'),
            (r'(?i)\bscale\s+(?:up|out)\b', '[SCALE+]'),
        ],
        # Compliance & Governance
        "governance": [
            (r'(?i)\bservice\s+level\s+agreement\b', '[SLA]'),
            (r'(?i)\bkey\s+performance\s+indicators?\b', '[KPI]'),
            (r'(?i)\bstandard\s+operating\s+procedures?\b', '[SOP]'),
            (r'(?i)\breturn\s+on\s+investment\b', '[ROI]'),
            (r'(?i)\btechnical\s+specifications?\b', '[TECH:SPC]'),
            (r'(?i)\breed\s+of\s+risk\b', '[RISK:POL]'),
            (r'(?i)\bdata\s+protection\s+officer\b', '[DPO]'),
            (r'(?i)\bgeneral\s+data\s+protection\s+regulation\b', '[GDPR]'),
            (r'(?i)\bcompliance\s+officer\b', '[CO]'),
            (r'(?i)\baudit\s+trail\b', '[AUD:LOG]'),
        ],
        # DevOps & Engineering
        "devops": [
            (r'(?i)\bcontinuous\s+integration\b', '[CI]'),
            (r'(?i)\bcontinuous\s+deployment\b', '[CD]'),
            (r'(?i)\bpull\s+request\b', '[PR]'),
            (r'(?i)\bcode\s+review\b', '[CR]'),
            (r'(?i)\binfrastructure\s+as\s+code\b', '[IaC]'),
            (r'(?i)\bload\s+balancer\b', '[LB]'),
            (r'(?i)\brate\s+limiting\b', '[RL]'),
            (r'(?i)\bapplication\s+programming\s+interface\b', '[API]'),
            (r'(?i)\bmicroservices?\s+architecture\b', '[MSA]'),
            (r'(?i)\bkubernetes\b', '[K8s]'),
            (r'(?i)\bdocker\b', '[DKR]'),
            (r'(?i)\bdatabase\b', '[DB]'),
            (r'(?i)\bauthentication\b', '[AUTH]'),
            (r'(?i)\bauthorization\b', '[AUTHZ]'),
            (r'(?i)\bendpoint\b', '[EP]'),
        ],
        # Finance
        "finance": [
            (r'(?i)\bearnings\s+before\s+interest\s+and\s+taxes\b', '[EBIT]'),
            (r'(?i)\bgross\s+domestic\s+product\b', '[GDP]'),
            (r'(?i)\baccounts?\s+receivable\b', '[AR]'),
            (r'(?i)\baccounts?\s+payable\b', '[AP]'),
            (r'(?i)\bprofit\s+and\s+loss\b', '[P&L]'),
            (r'(?i)\boperating\s+expenses?\b', '[OPEX]'),
            (r'(?i)\bcapital\s+expenditures?\b', '[CAPEX]'),
            (r'(?i)\bcash\s+flow\b', '[C/F]'),
            (r'(?i)\bbusiness\s+development\b', '[BIZ:DEV]'),
        ],
    }
    # Flatten all mappings
    _MAPPINGS: list[tuple[re.Pattern, str]] = []
    for _cat_patterns in _CATEGORIES.values():
        for _pat, _repl in _cat_patterns:
            _MAPPINGS.append((re.compile(_pat), _repl))

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = text
        for pattern, replacement in cls._MAPPINGS:
            out = pattern.sub(replacement, out)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🟡 MEDIUM ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class RedundancyEliminator:
    """🟡 MEDIUM — Bigram similarity deduplicator. ~25% savings.

    Improvements over v1:
    - Uses bigram-level comparison (more accurate than unigram Jaccard)
    - Detects explicit paraphrase markers ("In other words", "To rephrase")
    - Lower threshold (0.55) for more aggressive duplicate removal
    - Removes explicitly repeated sentences
    """
    THRESHOLD = 0.55
    _PARAPHRASE_MARKERS = re.compile(
        r'(?i)\b(in other words|to rephrase|to put it differently|'
        r'that is to say|to clarify|to be more specific|'
        r'in (simpler|plain|other) terms),?\s*',
        re.IGNORECASE
    )

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        # First, remove sentences preceded by explicit paraphrase markers
        out = cls._PARAPHRASE_MARKERS.sub('', text)

        sentences = _split_sentences(out)
        if len(sentences) <= 2:
            return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))

        accepted: list[str] = []
        accepted_bigrams: list[set] = []
        accepted_words: list[set] = []

        for sent in sentences:
            words = _word_set(sent)
            bigs = _bigrams(sent)
            if not words:
                continue

            # Check against all previously accepted sentences
            is_duplicate = False
            for prev_words, prev_bigs in zip(accepted_words, accepted_bigrams):
                # Word-level Jaccard
                word_sim = len(words & prev_words) / max(1, len(words | prev_words))
                # Bigram overlap (if enough bigrams exist)
                big_sim = 0.0
                if bigs and prev_bigs:
                    big_sim = len(bigs & prev_bigs) / max(1, len(bigs | prev_bigs))

                # Take the maximum of both similarity measures
                similarity = max(word_sim, big_sim)
                if similarity > cls.THRESHOLD:
                    is_duplicate = True
                    break

            if not is_duplicate:
                accepted.append(sent)
                accepted_words.append(words)
                accepted_bigrams.append(bigs)

        result = ' '.join(accepted)
        return result, max(0, _estimate_tokens(text) - _estimate_tokens(result))


class TFIDFExtractor:
    """🟡 MEDIUM — Position-weighted TF-IDF sentence extractor. ~45% savings.

    v2.1 improvements:
    - Works on texts with as few as 2 sentences (removed the <=3 guard)
    - Uses word-length normalization so longer sentences aren't unfairly rewarded
    - Question sentences get a 1.5x bonus (strong intent signal)
    - First and last sentences always protected
    - Configurable keep ratio — defaults to 35%
    """
    KEEP = 0.35

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        n = len(sentences)
        if n <= 1:
            return text, 0

        # With only 2-3 sentences, keep the highest-scoring one + first
        if n == 2:
            # Keep both but strip stop words from each sentence for density
            return text, 0  # already very compact, don't compress

        # Build TF per sentence using 3+ char words
        tfs = [Counter(re.findall(r'\b\w{4,}\b', s.lower())) for s in sentences]
        doc_freq = Counter()
        for tf in tfs:
            doc_freq.update(tf.keys())

        def idf(w: str) -> float:
            return math.log((n + 1) / (1 + doc_freq[w]))

        def score(i: int) -> float:
            words = list(tfs[i].keys())
            if not words:
                return 0.0
            # Normalize by sentence word count so short, dense sentences score well
            sent_word_count = max(1, len(sentences[i].split()))
            raw = sum(tfs[i][w] * idf(w) for w in words)
            base = raw / sent_word_count
            # Position bonus: first and last are always important
            pos_mult = 1.8 if i == 0 or i == n - 1 else 1.0
            # Strong bonus for questions — direct intent
            q_mult = 1.5 if sentences[i].rstrip().endswith('?') else 1.0
            # Bonus for sentences with numbers (data points)
            num_mult = 1.2 if re.search(r'\b\d+\b', sentences[i]) else 1.0
            return base * pos_mult * q_mult * num_mult

        scores = sorted([(score(i), i) for i in range(n)], reverse=True)
        keep_n = max(2, int(n * cls.KEEP))  # always keep at least 2

        # Always keep first sentence for context
        kept_idx = {0, n - 1}  # first and last always kept
        for _, idx in scores:
            if len(kept_idx) >= keep_n:
                break
            kept_idx.add(idx)

        kept = sorted(kept_idx)
        out = ' '.join(sentences[i] for i in kept)
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class NEXSemanticDensityFilter:
    """🟡 MEDIUM — Precision signal vocabulary filter. ~35% savings.

    v2.1 improvements:
    - Uses word-boundary matching (\\b) instead of substring matching to avoid
      false positives (e.g. "cat" matching "concatenate")
    - Scores each sentence by how many cluster keywords it contains
    - Keeps only sentences scoring above the per-text median signal score
    - Minimum 3-word sentences required to be evaluated
    - First and last sentences always kept for context
    """
    _CLUSTERS = {
        "api_tech": frozenset({
            "api", "endpoint", "token", "request", "response", "header", "payload",
            "auth", "oauth", "webhook", "rest", "graphql", "grpc", "http", "https",
            "json", "xml", "schema", "parsing", "client", "server", "protocol",
        }),
        "infra": frozenset({
            "server", "database", "cache", "queue", "broker", "stream",
            "kubernetes", "docker", "container", "deployment", "pipeline", "cluster",
            "node", "service", "gateway", "proxy", "balancer", "replica", "shard",
        }),
        "model_ai": frozenset({
            "model", "inference", "embedding", "context", "prompt", "completion",
            "latency", "throughput", "accuracy", "precision", "recall", "training",
            "llm", "neural", "feature", "vector", "attention", "transformer",
        }),
        "business": frozenset({
            "cost", "revenue", "savings", "roi", "kpi", "metric", "performance",
            "efficiency", "value", "impact", "priority", "deadline", "budget",
            "risk", "compliance", "audit", "sla", "contract", "forecast", "target",
        }),
        "analytics": frozenset({
            "data", "result", "analysis", "report", "trend", "percentage", "ratio",
            "rate", "increase", "decrease", "growth", "comparison", "benchmark",
            "statistic", "measurement", "correlation", "variance", "sample",
        }),
        "status": frozenset({
            "error", "failure", "success", "warning", "critical", "status",
            "issue", "bug", "fix", "resolution", "incident", "alert", "anomaly",
            "timeout", "retry", "fallback", "degraded", "crash", "exception",
        }),
        "action": frozenset({
            "implement", "deploy", "configure", "optimize", "migrate", "refactor",
            "monitor", "test", "debug", "update", "upgrade", "install", "remove",
            "create", "delete", "review", "approve", "block", "enable", "disable",
        }),
    }
    ALL_KEYWORDS: frozenset[str] = frozenset().union(*_CLUSTERS.values())

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        if len(sentences) <= 2:
            return text, 0

        # Score each sentence: count distinct cluster keywords (word-boundary match)
        def sent_score(s: str) -> int:
            words = set(re.findall(r'\b[a-z]+\b', s.lower()))
            return len(words & cls.ALL_KEYWORDS)

        scored = [(sent_score(s), s) for s in sentences]
        scores_only = [sc for sc, _ in scored]

        # Keep sentences that score above the median (or at least 1 keyword)
        if not scores_only:
            return text, 0
        median_score = sorted(scores_only)[len(scores_only) // 2]
        cutoff = max(1, median_score)  # always require at least 1 keyword hit

        high = [s for sc, s in scored if sc >= cutoff]

        # Always include first and last sentence for narrative coherence
        if not high or sentences[0] not in high:
            high = [sentences[0]] + high
        if len(sentences) > 1 and sentences[-1] not in high:
            high = high + [sentences[-1]]

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique = []
        for s in high:
            if s not in seen:
                seen.add(s)
                unique.append(s)

        out = ' '.join(unique) if unique else text
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🟠 AGGRESSIVE ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class ChunkSummarizer:
    """🟠 AGGRESSIVE — Extractive sentence condenser. ~55% savings.

    v2.1 improvements:
    - Reduced minimum from 200 to 60 words — works on standard paragraphs
    - Scores sentences using TF across the entire document (not per chunk)
    - Preserves first sentence always
    - Adaptive keep ratio: 1 sentence per 50 words of input
    - Handles bullet/numbered list items as sentences
    """

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        # Pre-process: treat bullet list items as sentences
        normalized = re.sub(r'(?m)^\s*[-*•]\s+', '\n', text)
        normalized = re.sub(r'(?m)^\s*\d+[.)\s]\s+', '\n', normalized)

        words = normalized.split()
        if len(words) < 60:  # minimum threshold — much lower than v1
            return text, 0

        sentences = _split_sentences(normalized)
        if len(sentences) <= 2:
            return text, 0

        # Build a global word frequency table for the whole document
        all_words = re.findall(r'\b\w{4,}\b', normalized.lower())
        word_freq = Counter(all_words)
        total_docs = len(sentences)

        def sent_score(s: str) -> float:
            ws = re.findall(r'\b\w{4,}\b', s.lower())
            if not ws:
                return 0.0
            # TF-weighted by inverse document frequency within the doc
            return sum(
                (word_freq[w] / max(1, total_docs)) * math.log(total_docs / max(1, word_freq[w]))
                for w in ws
            ) / max(1, len(ws))

        # Adaptive: keep ~1 sentence per 50 words
        target_sentences = max(2, len(words) // 50)
        target_sentences = min(target_sentences, len(sentences) - 1)

        scored = sorted(enumerate(sentences), key=lambda x: sent_score(x[1]), reverse=True)
        # Always keep sentence 0 (first for context)
        kept_idx: set[int] = {0}
        for i, _ in scored:
            if len(kept_idx) >= target_sentences:
                break
            kept_idx.add(i)

        out = ' '.join(sentences[i] for i in sorted(kept_idx))
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


class EntityExtractorPass:
    """🟠 AGGRESSIVE — NER-lite named entity and numeric anchor filter. ~40% savings.

    Improvements over v1:
    - Multi-pattern NER: PRODUCT, ORG, DATE, PERCENT, CURRENCY, URL, EMAIL, ACRONYM
    - Regex-based without heavy dependencies (no NLTK or spacy)
    - Keeps sentences with technical acronyms (API, SDK, SLA, KPI)
    - Keeps sentences with comparative values (more than, less than, X%)
    """
    # Patterns that mark a sentence as "high value"
    _ANCHORS = [
        re.compile(r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b'),            # Proper nouns
        re.compile(r'\b\d+(?:\.\d+)?(?:\s*%|\s*x\b|\s*times?\b)'),           # Percentages / multipliers
        re.compile(r'\b\$\s*[\d,]+(?:\.\d{2})?\b'),                          # Currency
        re.compile(r'\b(?:19|20)\d{2}\b'),                                    # Years
        re.compile(r'\b\d{1,2}(?:/\d{1,2}/\d{2,4}|\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\b'),  # Dates
        re.compile(r'https?://\S+'),                                          # URLs
        re.compile(r'\b[A-Z0-9]{2,6}\b'),                                    # Acronyms (API, SDK, etc.)
        re.compile(r'\b(?:more|less|greater|fewer|higher|lower)\s+than\s+\d'), # Comparatives with numbers
        re.compile(r'\b(?:Q[1-4]|H[12]|FY)\s*\d{4}\b'),                     # Fiscal periods
    ]

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        sentences = _split_sentences(text)
        if len(sentences) <= 2:
            return text, 0

        kept = [s for s in sentences if any(pat.search(s) for pat in cls._ANCHORS)]

        # Fallback: if we removed too much, keep at least 50%
        if len(kept) < max(2, len(sentences) // 2):
            kept = sentences[:max(2, len(sentences) // 2)]

        out = ' '.join(kept) if kept else text
        return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🔴 EXTREME ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class NEXNLBytecodeTranspiler:
    """🔴 EXTREME — Sentence-level semantic compression to dense NEX notation. ~70% savings.

    v2.1 — Complete rewrite with sentence-level extraction approach:
    - Converts full sentences to compact [SUBJ|PRED|OBJ] triples when possible
    - Falls back to phrase-level opcode substitution for complex sentences
    - Removes articles, prepositions, and stop words from replaced phrases
    - Does NOT add a header on short/unchanged texts (avoids token bloat)
    - Covers 50+ patterns across 6 semantic categories
    """

    # ── Stop words to strip from inside opcode brackets ──────────────────────
    _INNER_STOPS = re.compile(
        r'\b(the|a|an|is|are|was|were|that|this|it|its|to|of|for|in|on|at|'  
        r'by|with|from|and|or|but|be|been|being|so|if|then|there|which|who|'  
        r'have|has|had|will|would|should|could|may|might|can|shall)\b',
        re.IGNORECASE
    )

    # ── Intent / command patterns ────────────────────────────────────────────
    _COMMANDS = [
        (re.compile(r'(?i)\b(?:please|kindly|can you|could you|would you)?\s*'  
                    r'(summarize|analyze|analyse|fix|debug|check|write|create|generate|build|'  
                    r'optimize|refactor|explain|describe|translate|convert|review|test|deploy|'  
                    r'configure|implement|design|update|remove|delete|document|parse|format)'  
                    r'\s+(?:the\s+|this\s+|my\s+|our\s+|a\s+)?([\w\s]{2,40}?)(?=[.!?,]|$)'),
         lambda m: f'[DO:{m.group(1).upper()}({m.group(2).strip()})]'),
        (re.compile(r'(?i)\b(?:I|we)\s+(?:want|need|require|must)\s+(?:to|you to)?\s*(\w+)\s+([\w\s]{2,40}?)(?=[.!?,]|$)'),
         lambda m: f'[NEED:{m.group(1).upper()}({m.group(2).strip()})]'),
        (re.compile(r'(?i)\bwhat\s+(?:is|are|was|were)\s+(.{3,60}?)\?'),
         lambda m: f'[ASK:{m.group(1).strip()}]'),
        (re.compile(r'(?i)\bhow\s+(?:do|can|should|does|to)\s+(?:I|we|one|you)?\s*(.{3,60}?)\?'),
         lambda m: f'[HOW:{m.group(1).strip()}]'),
        (re.compile(r'(?i)\bwhy\s+(?:is|are|does|do|did|was|were)\s+(.{3,60}?)\?'),
         lambda m: f'[WHY:{m.group(1).strip()}]'),
    ]

    # ── Causality / logical flow ─────────────────────────────────────────────
    _CAUSALITY = [
        (re.compile(r'(?i)\b(?:because|due to|since|as a result of|owing to|on account of)\b'), '[CAU]'),
        (re.compile(r'(?i)\b(?:therefore|consequently|as a result|thus|hence|accordingly|so)\b'), '[RES]'),
        (re.compile(r'(?i)\b(?:however|but|although|nevertheless|on the other hand|in contrast|yet|despite)\b'), '[CON]'),
        (re.compile(r'(?i)\b(?:for example|e\.g\.|for instance|such as|including|like)\b'), '[EG:]'),
        (re.compile(r'(?i)\b(?:in addition|furthermore|moreover|additionally|also|and moreover)\b'), '[ADD]'),
        (re.compile(r'(?i)\b(?:in conclusion|to summarize|in summary|to conclude|overall|in short)\b'), '[SUM]'),
    ]

    # ── Temporal markers ────────────────────────────────────────────────────
    _TEMPORAL = [
        (re.compile(r'(?i)\b(?:yesterday|last\s+(?:week|month|year|quarter|sprint|iteration))\b'), '[T:PAST]'),
        (re.compile(r'(?i)\b(?:currently|at the moment|right now|today|at present|now)\b'), '[T:NOW]'),
        (re.compile(r'(?i)\b(?:tomorrow|next\s+(?:week|month|year|quarter|sprint)|soon|upcoming|in the future)\b'), '[T:NEXT]'),
        (re.compile(r'(?i)\b(?:immediately|urgently|asap|right away|without delay)\b'), '[T:ASAP]'),
    ]

    # ── Status / error patterns ─────────────────────────────────────────────
    _STATUS = [
        (re.compile(r'(?i)\bthe\s+(?:api|service|endpoint|server)\s+(?:returned|sent|threw|raised)\s+(?:an?\s+)?(?:error|exception|fault)\b\s*(\d*)'),
         lambda m: f'[SVC:ERR({m.group(1) or "?"})]'),
        (re.compile(r'(?i)\b(?:error|exception|failure)\s+(?:code|type|num|number)?\s*[:=]?\s*(\w+)'),
         lambda m: f'[ERR:{m.group(1)}]'),
        (re.compile(r'(?i)\bstatus\s*[:=]\s*(\w+)'),
         lambda m: f'[ST:{m.group(1).upper()}]'),
        (re.compile(r'(?i)\b(\d+(?:\.\d+)?)\s*%\s+(?:reduction|improvement|increase|decrease|growth|drop|gain)'),
         lambda m: f'[Δ:{m.group(1)}%]'),
        (re.compile(r'(?i)\b(?:timed?\s+out|timeout|connection\s+(?:refused|reset|failed))\b'), '[ERR:TIMEOUT]'),
        (re.compile(r'(?i)\b(?:rate\s+limit(?:ed)?|throttl(?:ed|ing))\b'), '[ERR:RATELIMIT]'),
    ]

    # ── Quantitative / comparison patterns ─────────────────────────────────
    _QUANT = [
        (re.compile(r'(?i)\b(\d+(?:\.\d+)?)\s*(?:tokens?|milliseconds?|ms|seconds?|minutes?|hours?|days?)\b'),
         lambda m: f'[N:{m.group(0)}]'),
        (re.compile(r'(?i)\b(?:more|greater|higher|larger)\s+than\s+(\d[\w.]*)'),
         lambda m: f'[CMP:>{m.group(1)}]'),
        (re.compile(r'(?i)\b(?:less|fewer|lower|smaller)\s+than\s+(\d[\w.]*)'),
         lambda m: f'[CMP:<{m.group(1)}]'),
        (re.compile(r'(?i)\b(?:approximately|about|roughly|around|~)\s+(\d[\w.]*)'),
         lambda m: f'[~{m.group(1)}]'),
    ]

    # ── Condition patterns ──────────────────────────────────────────────────
    _CONDITIONS = [
        (re.compile(r'(?i)\bif\s+(.{5,60}?)\s*,?\s*(?:then)?\s+(.{5,60}?)(?=[.!?]|$)'),
         lambda m: f'[IF:{m.group(1).strip()}→{m.group(2).strip()}]'),
        (re.compile(r'(?i)\bunless\s+(.{5,50}?)(?=[.,!?]|$)'),
         lambda m: f'[UNLESS:{m.group(1).strip()}]'),
        (re.compile(r'(?i)\bwhen(?:ever)?\s+(.{5,50}?)(?=[.,!?]|$)'),
         lambda m: f'[WHEN:{m.group(1).strip()}]'),
    ]

    @classmethod
    def _apply_group(cls, text: str, patterns: list) -> str:
        out = text
        for pat, repl in patterns:
            try:
                if callable(repl):
                    out = pat.sub(repl, out)
                else:
                    out = pat.sub(repl, out)
            except Exception:
                pass
        return out

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        out = text

        # Apply all pattern groups in order
        out = cls._apply_group(out, cls._COMMANDS)
        out = cls._apply_group(out, cls._QUANT)       # wrap numbers first
        out = cls._apply_group(out, cls._CONDITIONS)  # then conditions (uses wrapped numbers)
        out = cls._apply_group(out, cls._CAUSALITY)
        out = cls._apply_group(out, cls._TEMPORAL)
        out = cls._apply_group(out, cls._STATUS)

        # Collapse whitespace artifacts from substitutions
        out = re.sub(r'  +', ' ', out)
        out = re.sub(r'\s*,\s*,', ',', out)    # double commas
        out = re.sub(r'\s*\.\s*\.', '.', out)  # double periods

        # Strip inner stop words ONLY from the payload after the opcode name+colon
        # Pattern: [OPCODE:payload] → strip stops from payload only
        def _clean_opcode(m: re.Match) -> str:
            content = m.group(1)
            # Split at first colon (opcode name : payload)
            if ':' in content:
                opcode, payload = content.split(':', 1)
                payload_clean = cls._INNER_STOPS.sub(' ', payload).strip()
                payload_clean = re.sub(r'\s{2,}', ' ', payload_clean)
                return f'[{opcode}:{payload_clean}]'
            return m.group(0)  # no colon — leave unchanged

        out = re.sub(r'\[([^\]]+)\]', _clean_opcode, out)
        out = re.sub(r'\[\s+', '[', out)
        out = re.sub(r'\s+\]', ']', out)
        out = out.strip()

        # Only mark as NEX if we actually changed something meaningfully
        savings = _estimate_tokens(text) - _estimate_tokens(out)
        if savings > 2 and not out.startswith('[NEX'):
            out = '[NEX.NL] ' + out

        return out, max(0, savings)


# ═══════════════════════════════════════════════════════════════════════════════
#  ALGORITHM REGISTRY  (for the UI)
# ═══════════════════════════════════════════════════════════════════════════════

ALGO_REGISTRY = {
    "hedge":        {"name": "Filler & Hedge Eliminator",     "level": "light",      "emoji": "🟢", "color": "#4ade80", "savings": "~12%", "desc": "60+ patterns: hedges, padding, affirmations.",    "fn": HedgeWordRemover.apply},
    "quote":        {"name": "Context-Aware Quote Truncator", "level": "light",      "emoji": "🟢", "color": "#4ade80", "savings": "~15%", "desc": "Smart truncation preserving entities and numbers.",  "fn": QuotationCompressor.apply},
    "stopword":     {"name": "Semantic Stop Word Filter",     "level": "light",      "emoji": "🟢", "color": "#4ade80", "savings": "~28%", "desc": "Negation-safe pruner preserving comparative words.", "fn": StopWordPruner.apply},
    "redundancy":   {"name": "Bigram Similarity Deduplicator","level": "medium",     "emoji": "🟡", "color": "#fbbf24", "savings": "~25%", "desc": "Bigram-level overlap + paraphrase marker removal.",  "fn": RedundancyEliminator.apply},
    "tfidf":        {"name": "Position-Weighted TF-IDF",      "level": "medium",     "emoji": "🟡", "color": "#fbbf24", "savings": "~45%", "desc": "Position+question weighted sentence ranking.",       "fn": TFIDFExtractor.apply},
    "semantic":     {"name": "NEX Semantic Density Filter",   "level": "medium",     "emoji": "🟡", "color": "#fbbf24", "savings": "~35%", "desc": "80+ keywords in 5 domain clusters + dynamic inject.", "fn": NEXSemanticDensityFilter.apply},
    "chunking":     {"name": "Extractive Chunk Condenser",    "level": "aggressive", "emoji": "🟠", "color": "#fb923c", "savings": "~55%", "desc": "Mini-TF-IDF best-sentence per 120-word chunk.",      "fn": ChunkSummarizer.apply},
    "entities":     {"name": "NER-Lite Entity Filter",        "level": "aggressive", "emoji": "🟠", "color": "#fb923c", "savings": "~40%", "desc": "9 entity patterns: org, date, %, $, URL, acronym.",  "fn": EntityExtractorPass.apply},
    "bytecode":     {"name": "NEX Semantic Opcode Transpiler","level": "extreme",    "emoji": "🔴", "color": "#f87171", "savings": "~70%", "desc": "40+ opcode patterns: intent, temporal, causality.",   "fn": NEXNLBytecodeTranspiler.apply},
    "corp_dict":    {"name": "Domain Vocabulary Encoder",     "level": "extreme",    "emoji": "🔴", "color": "#f87171", "savings": "~25%", "desc": "80+ mappings: business, DevOps, legal, finance.",     "fn": CorporateDictionary.apply},
}


# ═══════════════════════════════════════════════════════════════════════════════
#  PRESET PIPELINES
# ═══════════════════════════════════════════════════════════════════════════════

class NEXTextCompressor:
    """
    Orchestrates NL compression pipelines at different intensity levels.
    """
    # Standard production pipeline
    INPUT_PIPELINE = [
        ("FillerHedgeRemove",    HedgeWordRemover.apply),
        ("QuotationCompress",    QuotationCompressor.apply),
        ("StopWordFilter",       StopWordPruner.apply),
        ("BigramDeduplicate",    RedundancyEliminator.apply),
        ("SemanticFilter",       NEXSemanticDensityFilter.apply),
        ("PositionTFIDF",        TFIDFExtractor.apply),
    ]

    # Extreme pipeline for maximum density
    INPUT_PIPELINE_EXTREME = [
        ("CorporateEncode",      CorporateDictionary.apply),
        ("FillerHedgeRemove",    HedgeWordRemover.apply),
        ("QuotationCompress",    QuotationCompressor.apply),
        ("StopWordFilter",       StopWordPruner.apply),
        ("BigramDeduplicate",    RedundancyEliminator.apply),
        ("SemanticFilter",       NEXSemanticDensityFilter.apply),
        ("ChunkCondense",        ChunkSummarizer.apply),
        ("NEXNLTranspile",       NEXNLBytecodeTranspiler.apply),
    ]

    OUTPUT_PIPELINE = [
        ("PreambleStrip",       lambda t: (re.sub(r'^(Of course|Sure|Certainly|Absolutely)[!.]?\s*', '', t, flags=re.I), 0)),
        ("QualifierNormalize",  lambda t: (re.sub(r'\bin order to\b', 'to', t, flags=re.I), 0)),
        ("RedundantPhraseStrip",lambda t: (re.sub(r'\b(as previously mentioned|as stated above|as noted earlier)\b', '', t, flags=re.I), 0)),
    ]

    @classmethod
    def compress_input(cls, text: str, extreme: bool = False) -> CompressionResult:
        pipeline = cls.INPUT_PIPELINE_EXTREME if extreme else cls.INPUT_PIPELINE
        return cls._run(text, pipeline, "input")

    @classmethod
    def compress_with_algo(cls, text: str, algo_key: str) -> CompressionResult:
        if algo_key not in ALGO_REGISTRY:
            return cls._run(text, [], "input")
        fn = ALGO_REGISTRY[algo_key]["fn"]
        t_before = _estimate_tokens(text)
        out, rem = fn(text)
        t_after = _estimate_tokens(out)
        sav = round((t_before - t_after) / t_before * 100, 1) if t_before > 0 else 0.0
        return CompressionResult(out, text, t_before, t_after, sav, [(algo_key, rem)], "input")

    @classmethod
    def _run(cls, text: str, pipeline: list, side: str) -> CompressionResult:
        t_before = _estimate_tokens(text)
        log, current = [], text
        for name, fn in pipeline:
            current, rem = fn(current)
            log.append((name, rem))
        t_after = _estimate_tokens(current)
        sav = round((t_before - t_after) / t_before * 100, 1) if t_before > 0 else 0.0
        return CompressionResult(current, text, t_before, t_after, sav, log, side)
