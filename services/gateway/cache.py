"""
Firma-KI Gateway — Domain-Specific Semantic Cache
Embedding-based similarity caching with Mismatch Cost Algorithm.
Replaces the legacy SHA-256 exact-match cache.
"""
import hashlib
import json
import math
from models.gateway import CacheEntry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select


class SemanticCache:
    """
    Domain-Specific Semantic Cache.
    """

    DEFAULT_SIMILARITY_THRESHOLD = 0.85
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
        normalized = json.dumps(messages, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def _compute_embedding(self, text: str) -> list[float]:
        vector = [0.0] * 128
        text_lower = text.lower()
        for i in range(len(text_lower) - 2):
            trigram = text_lower[i:i+3]
            bucket = hash(trigram) % 128
            sign = 1 if (hash(trigram + '_sign') % 2 == 0) else -1
            vector[bucket] += sign
        magnitude = math.sqrt(sum(v * v for v in vector))
        if magnitude > 0:
            vector = [v / magnitude for v in vector]
        return vector

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if len(vec_a) != len(vec_b):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot_product / (mag_a * mag_b)

    async def get(self, db: AsyncSession, messages) -> tuple:
        prompt_hash = self._compute_hash(messages)

        # Level 1: Exact match
        stmt = select(CacheEntry).where(
            CacheEntry.organization_id == self.organization.id,
            CacheEntry.prompt_hash == prompt_hash
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()

        if entry:
            entry.hit_count += 1
            await db.commit()
            return json.loads(entry.response_json), True, {
                'match_type': 'exact',
                'similarity': 1.0,
            }

        # Level 2: Semantic similarity search
        query_text = self._extract_query_text(messages)
        query_embedding = self._compute_embedding(query_text)

        stmt = select(CacheEntry).where(
            CacheEntry.organization_id == self.organization.id,
            CacheEntry.embedding_model == self.embedding_model,
            CacheEntry.embedding_vector != ''
        ).limit(100)
        
        result = await db.execute(stmt)
        candidates = result.scalars().all()

        best_match = None
        best_similarity = 0.0

        for candidate in candidates:
            try:
                stored_embedding = json.loads(candidate.embedding_vector)
            except (json.JSONDecodeError, TypeError):
                continue
            
            similarity = self._cosine_similarity(query_embedding, stored_embedding)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate

        if best_match and best_similarity >= self.similarity_threshold:
            cached_tokens = best_match.tokens_used
            mismatch_delta = 1.0 - best_similarity
            regen_cost = cached_tokens * self.DEFAULT_REGEN_COST_WEIGHT
            mismatch_penalty = mismatch_delta * 10

            if regen_cost > mismatch_penalty:
                best_match.hit_count += 1
                await db.commit()
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

    async def set(self, db: AsyncSession, messages, response, tokens_used=0):
        prompt_hash = self._compute_hash(messages)
        query_text = self._extract_query_text(messages)
        embedding = self._compute_embedding(query_text)

        stmt = select(CacheEntry).where(
            CacheEntry.organization_id == self.organization.id,
            CacheEntry.prompt_hash == prompt_hash
        )
        result = await db.execute(stmt)
        entry = result.scalar_one_or_none()
        
        if entry:
            entry.response_json = json.dumps(response, ensure_ascii=False)
            entry.tokens_used = tokens_used
            entry.embedding_vector = json.dumps(embedding)
            entry.embedding_model = self.embedding_model
            entry.domain = self.domain
        else:
            entry = CacheEntry(
                organization_id=self.organization.id,
                prompt_hash=prompt_hash,
                response_json=json.dumps(response, ensure_ascii=False),
                tokens_used=tokens_used,
                embedding_vector=json.dumps(embedding),
                embedding_model=self.embedding_model,
                domain=self.domain
            )
            db.add(entry)
            
        await db.commit()

    @staticmethod
    def _extract_query_text(messages) -> str:
        user_messages = [
            m.get('content', '') for m in messages
            if m.get('role') in ('user', 'human')
        ]
        if user_messages:
            return user_messages[-1]
        return ' '.join(m.get('content', '') for m in messages if m.get('content'))
