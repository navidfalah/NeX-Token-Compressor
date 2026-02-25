"""
Firma-KI Gateway — Semantic Cache
SHA-256 hash-based prompt caching layer.
"""
import hashlib
import json
from .models import CacheEntry


class SemanticCache:
    """
    Caches LLM responses by the SHA-256 hash of the normalized prompt.
    """

    def __init__(self, organization):
        self.organization = organization

    def _compute_hash(self, messages):
        """Compute a deterministic hash of the messages."""
        normalized = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def get(self, messages):
        """
        Check cache for a matching prompt.
        Returns (cache_entry, hit) tuple.
        """
        prompt_hash = self._compute_hash(messages)

        try:
            entry = CacheEntry.objects.get(
                organization=self.organization,
                prompt_hash=prompt_hash,
            )
            entry.hit_count += 1
            entry.save(update_fields=['hit_count', 'last_hit_at'])
            return json.loads(entry.response_json), True
        except CacheEntry.DoesNotExist:
            return None, False

    def set(self, messages, response, tokens_used=0):
        """
        Store a response in the cache.
        """
        prompt_hash = self._compute_hash(messages)

        CacheEntry.objects.update_or_create(
            organization=self.organization,
            prompt_hash=prompt_hash,
            defaults={
                'response_json': json.dumps(response, ensure_ascii=False),
                'tokens_used': tokens_used,
            }
        )
