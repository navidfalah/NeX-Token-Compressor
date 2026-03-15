"""
Firma-KI Gateway — Dynamic Cascade Router (MVP Edition)
Tier 1 (DeepSeek) -> Tier 2 (Gemini)
"""
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models.dashboard import CascadeConfig

class CascadeRouter:
    """
    Dynamic Cascade Routing.
    Routes requests based on deterministic heuristics and response confidence.
    """

    DEFAULT_THRESHOLD = 0.7

    COMPLEXITY_KEYWORDS = [
        r'\bcalculate\b', r'\bderive\b', r'\bprove\b', r'\bintegrate\b', 
        r'\bdifferential\b', r'\bequation\b', r'\balgorithm\b', r'\boptimize\b',
        r'\brefactor\b', r'\barchitect\b', r'\bdesign pattern\b', r'\bunified\b',
        r'\bquantum\b', r'\bcryptograph\b', r'\bcomplex\b', r'\banalyze\b'
    ]
    
    COMPLEXITY_LENGTH_THRESHOLD = 2000 # words

    UNCERTAINTY_PATTERNS = [
        (r'\bI think\b', 0.15), (r'\bI believe\b', 0.12), (r'\bpossibly\b', 0.15),
        (r'\bperhaps\b', 0.15), (r'\bmaybe\b', 0.15), (r'\bnot sure\b', 0.20),
        (r"\bI don't know\b", 0.30), (r'\bunsure\b', 0.20),
    ]

    def __init__(self, cheap_provider=None, heavyweight_provider=None,
                 confidence_threshold: float = None):
        self.cheap_provider = cheap_provider
        self.heavyweight_provider = heavyweight_provider
        self.threshold = confidence_threshold or self.DEFAULT_THRESHOLD

    def is_complex(self, prompt: str) -> bool:
        """Determines if a prompt is complex based on deterministic heuristics."""
        if len(prompt.split()) > self.COMPLEXITY_LENGTH_THRESHOLD:
            return True
        for pattern in self.COMPLEXITY_KEYWORDS:
            if re.search(pattern, prompt, re.IGNORECASE):
                return True
        if "[HEAVY]" in prompt.upper() or "[COMPLEX]" in prompt.upper():
            return True
        return False

    def estimate_confidence(self, response_text: str) -> float:
        """Estimates confidence score of a response."""
        if not response_text or not response_text.strip():
            return 0.0
        penalty = 0.0
        for pattern, weight in self.UNCERTAINTY_PATTERNS:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            penalty += weight * len(matches)
        
        return max(0.0, 1.0 - penalty)

    async def route(self, messages: list, call_fn_async) -> tuple[str, dict]:
        """
        Execute the Dynamic Cascade Routing strategy.
        Tier 1: DeepSeek (Default)
        Tier 2: Gemini (Escalation)
        """
        metadata = {'strategy': 'dynamic_cascade', 'stages': []}
        user_prompt = messages[-1]['content'] if messages else ""
        
        # 1. Deterministic Check
        if self.is_complex(user_prompt):
            metadata['decision'] = 'direct_to_heavy'
            if self.heavyweight_provider:
                res, pt, ct = await call_fn_async(self.heavyweight_provider, messages)
                metadata['stages'].append({'heavy_model': {'prompt_tokens': pt, 'completion_tokens': ct}})
                return res, metadata

        # 2. Tier 1: DeepSeek
        if self.cheap_provider:
            cheap_res, pt, ct = await call_fn_async(self.cheap_provider, messages)
            confidence = self.estimate_confidence(cheap_res)
            
            metadata['stages'].append({
                'cheap_model': {
                    'prompt_tokens': pt, 
                    'completion_tokens': ct,
                    'confidence': confidence
                }
            })

            if confidence >= self.threshold:
                metadata['escalated'] = False
                return cheap_res, metadata
            
            metadata['escalated'] = True

        # 3. Tier 2: Gemini (Escalation)
        if self.heavyweight_provider:
            res, pt, ct = await call_fn_async(self.heavyweight_provider, messages)
            metadata['stages'].append({'heavy_model': {'prompt_tokens': pt, 'completion_tokens': ct}})
            return res, metadata

        return cheap_res if 'cheap_res' in locals() else "", metadata

class CascadeConfigLoader:
    @staticmethod
    async def load_for_organization_async(db: AsyncSession, organization) -> 'CascadeRouter':
        try:
            from sqlalchemy.orm import selectinload
            stmt = select(CascadeConfig).options(
                selectinload(CascadeConfig.cheap_provider),
                selectinload(CascadeConfig.heavyweight_provider)
            ).where(
                CascadeConfig.organization_id == organization.id,
                CascadeConfig.is_active == True
            )
            result = await db.execute(stmt)
            config = result.scalar_one_or_none()
            if config:
                return CascadeRouter(
                    cheap_provider=config.cheap_provider,
                    heavyweight_provider=config.heavyweight_provider,
                    confidence_threshold=config.confidence_threshold,
                )
        except Exception as e:
            print(f"Error loading cascade config: {e}")
        return CascadeRouter()
