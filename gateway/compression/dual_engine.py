"""
Firma-KI Gateway — Dual-Engine Generative Compression Matrix
Orchestrator that classifies input and routes to the appropriate compression pipeline.
"""
from .content_classifier import ContentClassifier
from .nlc_compressor import SCOPECompressor, EHPCCompressor
from .cac_compressor import ASTPruner, ExecutionTraceSummarizer


class DualEngineCompressor:
    """
    Dual-Engine Generative Compression Matrix.
    
    Routes incoming payloads through specialized compression pipelines:
      Pipeline A (NLC): SCOPE + EHPC for natural language
      Pipeline B (CAC): AST Pruning + Execution-Trace Summarization for code
    
    Provides maximum token reduction without context degradation by using
    content-appropriate compression strategies.
    """

    @classmethod
    def compress(cls, text: str, force_pipeline: str = None) -> tuple[str, dict]:
        """
        Compress text through the appropriate pipeline.
        
        Args:
            text: Input text to compress.
            force_pipeline: Override auto-detection ('nlc' or 'cac').
            
        Returns:
            (compressed_text, metadata) where metadata includes pipeline info,
            compression ratios, and sub-pipeline details.
        """
        if not text or not text.strip():
            return text, {'pipeline': 'none', 'reason': 'empty_input'}

        original_length = len(text)
        original_tokens = max(1, original_length // 4)

        # Classify content type
        if force_pipeline:
            content_type = force_pipeline
            classifier_confidence = 1.0
        else:
            content_type, classifier_confidence = ContentClassifier.classify(text)

        metadata = {
            'content_type': content_type,
            'classifier_confidence': classifier_confidence,
            'original_length': original_length,
            'original_tokens': original_tokens,
        }

        if content_type == 'nlc':
            compressed, pipeline_meta = cls._pipeline_a_nlc(text)
        else:
            compressed, pipeline_meta = cls._pipeline_b_cac(text)

        metadata['pipeline'] = pipeline_meta
        
        compressed_length = len(compressed)
        compressed_tokens = max(1, compressed_length // 4)
        
        metadata['compressed_length'] = compressed_length
        metadata['compressed_tokens'] = compressed_tokens
        metadata['compression_ratio'] = round(
            1 - (compressed_tokens / original_tokens), 4
        ) if original_tokens > 0 else 0.0
        metadata['reduction_pct'] = round(
            metadata['compression_ratio'] * 100, 1
        )

        return compressed, metadata

    @classmethod
    def compress_messages(cls, messages: list, force_pipeline: str = None) -> tuple[list, dict]:
        """
        Compress a list of OpenAI-format messages.
        
        Returns:
            (compressed_messages, aggregate_metadata)
        """
        compressed_messages = []
        total_original = 0
        total_compressed = 0
        pipeline_details = []

        for msg in messages:
            content = msg.get('content', '')
            
            # Don't compress system prompts that contain NEX instructions
            if msg.get('role') == 'system' and 'NEX Bytecode' in content:
                compressed_messages.append(msg)
                tokens = max(1, len(content) // 4)
                total_original += tokens
                total_compressed += tokens
                continue

            if content:
                compressed_text, meta = cls.compress(content, force_pipeline)
                total_original += meta.get('original_tokens', 0)
                total_compressed += meta.get('compressed_tokens', 0)
                pipeline_details.append(meta)
                compressed_messages.append({**msg, 'content': compressed_text})
            else:
                compressed_messages.append(msg)

        aggregate = {
            'total_original_tokens': total_original,
            'total_compressed_tokens': total_compressed,
            'total_reduction_pct': round(
                (1 - total_compressed / total_original) * 100, 1
            ) if total_original > 0 else 0.0,
            'message_count': len(messages),
            'pipeline_details': pipeline_details,
        }

        return compressed_messages, aggregate

    @classmethod
    def _pipeline_a_nlc(cls, text: str) -> tuple[str, dict]:
        """
        Pipeline A — Natural Language Compression.
        Stage 1: SCOPE (semantic chunking for long docs)
        Stage 2: EHPC (token-weight pruning)
        """
        pipeline_meta = {'name': 'Pipeline A (NLC)', 'stages': []}

        # Stage 1: SCOPE for long documents
        scoped_text, scope_meta = SCOPECompressor.compress(text)
        pipeline_meta['stages'].append({'scope': scope_meta})

        # Stage 2: EHPC token compression
        compressed, ehpc_meta = EHPCCompressor.compress(scoped_text)
        pipeline_meta['stages'].append({'ehpc': ehpc_meta})

        return compressed, pipeline_meta

    @classmethod
    def _pipeline_b_cac(cls, text: str) -> tuple[str, dict]:
        """
        Pipeline B — Code & Algorithmic Context Compression.
        
        Routes based on sub-type detection:
        - Stack traces / logs → Execution-Trace Summarization
        - Source code → AST Pruning
        """
        pipeline_meta = {'name': 'Pipeline B (CAC)', 'stages': []}

        # Check if this is a stack trace or log dump first
        if ContentClassifier.is_stack_trace(text) or ContentClassifier.is_log_dump(text):
            summarized, trace_meta = ExecutionTraceSummarizer.summarize(text)
            pipeline_meta['stages'].append({'trace_summarizer': trace_meta})
            return summarized, pipeline_meta

        # Otherwise, apply AST pruning
        pruned, ast_meta = ASTPruner.prune(text)
        pipeline_meta['stages'].append({'ast_pruner': ast_meta})

        return pruned, pipeline_meta
