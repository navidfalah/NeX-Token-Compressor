"""
Firma-KI Gateway — Domain-Specific Semantic Cache
Embedding-based similarity caching with Mismatch Cost Algorithm.
Replaces the legacy SHA-256 exact-match cache.
"""
import hashlib
import json
import math
from .models import CacheEntry


class SemanticCache:
    """
    Domain-Specific Semantic Cache.
    
    Operates on two levels:
      1. Exact-match: SHA-256 hash of normalized prompt (instant, free)
      2. Semantic-match: Cosine similarity of prompt embeddings (deeper, catches similar intents)
    
    The Mismatch Cost Algorithm dynamically evaluates whether a cached response
    is "good enough" or if the delta in context justifies generating a new inference.
    """

    # Similarity threshold: below this, the cached response is not used
    DEFAULT_SIMILARITY_THRESHOLD = 0.85

    # Cost of generating a new response (estimated tokens * cost per token)
    # Used by the Mismatch Cost Algorithm to decide cache vs. regenerate
    DEFAULT_REGEN_COST_WEIGHT = 0.001

    def __init__(self, organization, embedding_model: str = 'default',
                 similarity_threshold: float = None, domain: str = ''):
        self.organization = organization
        self.embedding_model = embedding_model
        self.similarity_threshold = (
            similarity_threshold or self.DEFAULT_SIMILARITY_THRESHOLD
        )
        self.domain = domain

    def _compute_hash(self, messages):
        """Compute a deterministic SHA-256 hash of the messages."""
        normalized = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def _compute_embedding(self, text: str) -> list[float]:
        """
        Compute a text embedding vector.
        
        Uses a lightweight bag-of-words TF-IDF-like embedding for zero-dependency
        semantic similarity. For production, this can be swapped with
        sentence-transformers or an API-based embedding endpoint.
        """
        # Lightweight character n-gram embedding (no external dependencies)
        # Generates a 128-dimensional vector from character trigrams
        vector = [0.0] * 128
        text_lower = text.lower()
        
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i+3]
            # Hash trigram to a bucket
            bucket = hash(trigram) % 128
            # Use hash sign for random projection
            sign = 1 if (hash(trigram + '_sign') % 2 == 0) else -1
            vector[bucket] += sign

        # L2 normalize
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]

        return vector

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec_a) != len(vec_b):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))
        
        if mag_a == 0 or mag_b == 0:
            return 0.0
        
        return dot_product / (mag_a * mag_b)

    def get(self, messages) -> tuple:
        """
        Check cache for a matching prompt using dual-level lookup.
        
        Level 1: Exact hash match (instant)
        Level 2: Semantic similarity search (deeper)
        
        Returns:
            (cached_response, cache_hit: bool, match_metadata: dict)
        """
        prompt_hash = self._compute_hash(messages)

        # Level 1: Exact match
        try:
            entry = CacheEntry.objects.get(
                organization=self.organization,
                prompt_hash=prompt_hash,
            )
            entry.hit_count += 1
            entry.save(update_fields=['hit_count', 'last_hit_at'])
            return json.loads(entry.response_json), True, {
                'match_type': 'exact',
                'similarity': 1.0,
            }
        except CacheEntry.DoesNotExist:
            pass

        # Level 2: Semantic similarity search
        query_text = self._extract_query_text(messages)
        query_embedding = self._compute_embedding(query_text)

        # Search all cache entries for this org with embeddings
        candidates = CacheEntry.objects.filter(
            organization=self.organization,
            embedding_model=self.embedding_model,
        ).exclude(embedding_vector='')

        best_match = None
        best_similarity = 0.0

        for entry in candidates[:100]:  # Limit search space
            try:
                stored_embedding = json.loads(entry.embedding_vector)
            except (json.JSONDecodeError, TypeError):
                continue

            similarity = self._cosine_similarity(query_embedding, stored_embedding)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = entry

        # Apply Mismatch Cost Algorithm
        if best_match and best_similarity >= self.similarity_threshold:
            # Check if the cost of regeneration justifies using a slightly
            # mismatched cached response
            cached_tokens = best_match.tokens_used
            mismatch_delta = 1.0 - best_similarity
            regen_cost = cached_tokens * self.DEFAULT_REGEN_COST_WEIGHT
            mismatch_penalty = mismatch_delta * 10  # Scale factor

            if regen_cost > mismatch_penalty:
                # Cheaper to use cached response
                best_match.hit_count += 1
                best_match.save(update_fields=['hit_count', 'last_hit_at'])
                return json.loads(best_match.response_json), True, {
                    'match_type': 'semantic',
                    'similarity': round(best_similarity, 4),
                    'mismatch_delta': round(mismatch_delta, 4),
                    'regen_cost': round(regen_cost, 4),
                    'decision': 'cache_hit_cost_efficient',
                }

        return None, False, {
            'match_type': 'none',
            'best_similarity': round(best_similarity, 4) if best_similarity > 0 else 0,
            'threshold': self.similarity_threshold,
        }

    def set(self, messages, response, tokens_used=0):
        """
        Store a response in the cache with its embedding vector.
        """
        prompt_hash = self._compute_hash(messages)
        query_text = self._extract_query_text(messages)
        embedding = self._compute_embedding(query_text)

        CacheEntry.objects.update_or_create(
            organization=self.organization,
            prompt_hash=prompt_hash,
            defaults={
                'response_json': json.dumps(response, ensure_ascii=False),
                'tokens_used': tokens_used,
                'embedding_vector': json.dumps(embedding),
                'embedding_model': self.embedding_model,
                'domain': self.domain,
            }
        )

    @staticmethod
    def _extract_query_text(messages) -> str:
        """Extract the primary query text from messages for embedding."""
        # Focus on user messages, prioritize the last one
        user_messages = [
            m.get('content', '') for m in messages
            if m.get('role') in ('user', 'human')
        ]
        if user_messages:
            return user_messages[-1]
        
        # Fallback: concatenate all content
        return ' '.join(m.get('content', '') for m in messages if m.get('content'))
