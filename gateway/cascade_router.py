"""
Firma-KI Gateway — Confidence-Driven Cascade Router
Dynamically routes requests based on real-time Uncertainty Estimation.
Default to cheap model → measure confidence → auto-escalate if uncertain.
"""
import re


class CascadeRouter:
    """
    Confidence-Driven Cascade Routing.
    
    All incoming requests default to a lightning-fast, ultra-cheap model.
    The router measures the model's 'confidence score' in the response.
    If the model exhibits high uncertainty or hallucination risks, the request
    is instantly escalated to a heavyweight model.
    
    Result: Enterprise-grade output quality at the absolute lowest possible
    average cost per query.
    """

    # Default confidence threshold — below this triggers escalation
    DEFAULT_THRESHOLD = 0.7

    # Uncertainty markers and their weights
    UNCERTAINTY_PATTERNS = [
        # Hedging language
        (r'\bI think\b', 0.15),
        (r'\bI believe\b', 0.12),
        (r'\bpossibly\b', 0.15),
        (r'\bperhaps\b', 0.15),
        (r'\bmaybe\b', 0.15),
        (r'\bprobably\b', 0.10),
        (r'\bmight\b', 0.10),
        (r'\bcould be\b', 0.12),
        (r'\bnot sure\b', 0.20),
        (r"\bI'm not certain\b", 0.25),
        (r"\bI don't know\b", 0.30),
        (r'\bunsure\b', 0.20),
        (r'\bapproximate(?:ly)?\b', 0.08),
        # Contradiction signals
        (r'\bhowever.*but\b', 0.10),
        (r'\bon the other hand\b', 0.08),
        # Hallucination risk signals
        (r'\bAs of my (?:last |knowledge )?(?:update|training)\b', 0.25),
        (r'\bI cannot (?:verify|confirm)\b', 0.20),
        (r'\bplease verify\b', 0.15),
        (r'\bthis information (?:may|might) (?:be|not be) (?:accurate|current)\b', 0.20),
    ]

    # Patterns indicating high confidence (boost score)
    CONFIDENCE_PATTERNS = [
        (r'\bdefinitely\b', 0.10),
        (r'\bcertainly\b', 0.10),
        (r'\bthe answer is\b', 0.08),
        (r'\bspecifically\b', 0.05),
        (r'\baccording to\b', 0.08),
        (r'\bcorrect(?:ly)?\b', 0.05),
    ]

    def __init__(self, cheap_provider=None, heavyweight_provider=None,
                 confidence_threshold: float = None):
        """
        Args:
            cheap_provider: AIProvider instance for the fast/cheap model
            heavyweight_provider: AIProvider instance for the powerful model
            confidence_threshold: Override default threshold (0.0-1.0)
        """
        self.cheap_provider = cheap_provider
        self.heavyweight_provider = heavyweight_provider
        self.threshold = confidence_threshold or self.DEFAULT_THRESHOLD

    def estimate_confidence(self, response_text: str) -> tuple[float, dict]:
        """
        Estimate confidence score of a model's response.
        
        Analyzes the response text for uncertainty markers, brevity,
        repetition, and coherence signals.
        
        Returns:
            (confidence_score, analysis_details) where score is 0.0-1.0
        """
        if not response_text or not response_text.strip():
            return 0.0, {'reason': 'empty_response', 'factors': {}}

        factors = {}
        penalty = 0.0
        boost = 0.0

        # Factor 1: Uncertainty language patterns
        for pattern, weight in self.UNCERTAINTY_PATTERNS:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            if matches:
                penalty += weight * len(matches)
                factors[f'uncertainty:{pattern}'] = len(matches)

        # Factor 2: Confidence language patterns (countervail)
        for pattern, weight in self.CONFIDENCE_PATTERNS:
            matches = re.findall(pattern, response_text, re.IGNORECASE)
            if matches:
                boost += weight * len(matches)
                factors[f'confidence:{pattern}'] = len(matches)

        # Factor 3: Response brevity (very short responses are suspicious)
        word_count = len(response_text.split())
        if word_count < 10:
            penalty += 0.25
            factors['brevity_penalty'] = word_count
        elif word_count < 5:
            penalty += 0.40
            factors['extreme_brevity'] = word_count

        # Factor 4: Repetition detection (sign of hallucination)
        sentences = re.split(r'[.!?]+', response_text)
        if len(sentences) > 3:
            unique_sentences = set(s.strip().lower() for s in sentences if s.strip())
            repetition_ratio = 1 - (len(unique_sentences) / len(sentences))
            if repetition_ratio > 0.3:
                penalty += repetition_ratio * 0.3
                factors['repetition_ratio'] = round(repetition_ratio, 3)

        # Factor 5: Contains code blocks (higher confidence, structured response)
        if re.search(r'```[\s\S]*?```', response_text):
            boost += 0.15
            factors['has_code_block'] = True

        # Factor 6: Contains specific data (numbers, URLs, references)
        data_matches = len(re.findall(r'\b\d+(?:\.\d+)?(?:%|€|\$|ms|s|MB|KB|GB)\b', response_text))
        if data_matches > 0:
            boost += min(data_matches * 0.03, 0.15)
            factors['specific_data_points'] = data_matches

        # Calculate final confidence score
        raw_score = 1.0 - penalty + boost
        confidence = max(0.0, min(1.0, raw_score))

        return confidence, {
            'penalty': round(penalty, 4),
            'boost': round(boost, 4),
            'raw_score': round(raw_score, 4),
            'factors': factors,
        }

    def should_escalate(self, response_text: str) -> tuple[bool, float, dict]:
        """
        Determine if a response should trigger escalation to heavyweight model.
        
        Returns:
            (should_escalate, confidence_score, analysis_details)
        """
        confidence, details = self.estimate_confidence(response_text)
        escalate = confidence < self.threshold
        
        details['threshold'] = self.threshold
        details['decision'] = 'escalate' if escalate else 'accept'
        
        return escalate, confidence, details

    def route(self, messages: list, call_fn) -> tuple[str, dict]:
        """
        Execute the cascade routing strategy.
        
        1. Call cheap model first
        2. Evaluate confidence
        3. If low confidence, re-call with heavyweight model
        
        Args:
            messages: OpenAI-format message list
            call_fn: Callable(provider, messages) -> (response_text, prompt_tokens, completion_tokens)
            
        Returns:
            (final_response_text, routing_metadata)
        """
        metadata = {'strategy': 'cascade', 'stages': []}

        # Stage 1: Cheap model
        if self.cheap_provider:
            cheap_response, p_tokens, c_tokens = call_fn(
                self.cheap_provider, messages
            )
            
            stage1_meta = {
                'model': getattr(self.cheap_provider, 'name', 'cheap'),
                'prompt_tokens': p_tokens,
                'completion_tokens': c_tokens,
            }

            escalate, confidence, analysis = self.should_escalate(cheap_response)
            stage1_meta['confidence'] = round(confidence, 4)
            stage1_meta['analysis'] = analysis
            metadata['stages'].append({'cheap_model': stage1_meta})

            if not escalate:
                metadata['final_model'] = stage1_meta['model']
                metadata['escalated'] = False
                metadata['total_cost_tokens'] = p_tokens + c_tokens
                return cheap_response, metadata

        # Stage 2: Heavyweight model (escalation)
        if self.heavyweight_provider:
            heavy_response, p_tokens, c_tokens = call_fn(
                self.heavyweight_provider, messages
            )
            
            stage2_meta = {
                'model': getattr(self.heavyweight_provider, 'name', 'heavyweight'),
                'prompt_tokens': p_tokens,
                'completion_tokens': c_tokens,
            }
            metadata['stages'].append({'heavyweight_model': stage2_meta})
            metadata['final_model'] = stage2_meta['model']
            metadata['escalated'] = True
            metadata['total_cost_tokens'] = p_tokens + c_tokens
            
            return heavy_response, metadata

        # Fallback: no providers configured, return cheap response
        metadata['escalated'] = False
        metadata['final_model'] = 'fallback'
        return cheap_response if 'cheap_response' in dir() else '', metadata


class CascadeConfigLoader:
    """
    Loads cascade routing configuration from the database.
    """
    
    @staticmethod
    def load_for_organization(organization) -> CascadeRouter:
        """
        Load or create cascade routing config for an organization.
        Returns a configured CascadeRouter instance.
        """
        try:
            from dashboard.models import CascadeConfig
            config = CascadeConfig.objects.select_related(
                'cheap_provider', 'heavyweight_provider'
            ).get(organization=organization, is_active=True)
            
            return CascadeRouter(
                cheap_provider=config.cheap_provider,
                heavyweight_provider=config.heavyweight_provider,
                confidence_threshold=config.confidence_threshold,
            )
        except Exception:
            # No cascade config found — return router with no providers
            # (will pass through without cascade logic)
            return CascadeRouter()
