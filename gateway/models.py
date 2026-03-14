"""
Firma-KI Gateway — Models
Semantic cache entries with embedding support, MCP tool registry, and edge node config.
"""
import uuid
from django.db import models


class CacheEntry(models.Model):
    """
    Cached response for a given prompt hash.
    Supports both exact-match (hash) and semantic (embedding) lookups.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='cache_entries'
    )
    prompt_hash = models.CharField(max_length=64, db_index=True)
    response_json = models.TextField()
    tokens_used = models.IntegerField(default=0)
    hit_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_hit_at = models.DateTimeField(auto_now=True)

    # Semantic cache fields
    embedding_vector = models.TextField(
        blank=True, default='',
        help_text='JSON-serialized embedding vector for semantic similarity search'
    )
    embedding_model = models.CharField(
        max_length=50, blank=True, default='default',
        help_text='Which embedding model generated the vector'
    )
    domain = models.CharField(
        max_length=50, blank=True, default='',
        help_text='Domain tag (e.g., medical, legal, finance) for domain-specific matching'
    )

    class Meta:
        unique_together = ('organization', 'prompt_hash')
        ordering = ['-last_hit_at']
        verbose_name = 'Cache Entry'
        verbose_name_plural = 'Cache Entries'

    def __str__(self):
        return f"Cache [{self.prompt_hash[:12]}...] hits={self.hit_count}"
