"""
Firma-KI Gateway — Content Classifier
Heuristic classifier that determines whether input is Natural Language or Code/Algorithm.
Routes to the appropriate compression pipeline (NLC or CAC).
"""
import re


class ContentClassifier:
    """
    Classifies incoming text payloads as either:
      - 'nlc' (Natural Language Content) → Pipeline A
      - 'cac' (Code & Algorithmic Content) → Pipeline B
    
    Uses heuristic scoring based on code pattern density.
    """

    # Code-indicative patterns and their weights
    CODE_PATTERNS = [
        # Language keywords
        (r'\b(def|class|import|from|return|async|await|yield)\s', 2.0),
        (r'\b(function|const|let|var|=>|require|export)\s', 2.0),
        (r'\b(public|private|protected|static|void|int|string)\s', 2.0),
        (r'\b(SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|JOIN)\b', 2.0),
        # Structural patterns
        (r'[{}\[\]();]', 0.3),          # Brackets and semicolons
        (r'^\s{2,}', 0.5),              # Indentation (multiline flag)
        (r'^\s*(#|//|/\*|\*)', 0.8),    # Comment markers
        (r'[a-zA-Z_]\w*\(.*?\)', 0.6),  # Function calls
        (r'[a-zA-Z_]\w*\.[a-zA-Z_]', 0.4),  # Dot notation
        (r'(==|!=|<=|>=|&&|\|\||::|->)', 0.7),  # Operators
        # Stack traces and logs
        (r'(Traceback|Exception|Error|at\s+\w+\.\w+\()', 1.5),
        (r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}', 1.0),  # Timestamps in logs
        (r'(WARN|INFO|DEBUG|ERROR|FATAL)\s', 1.0),
    ]

    # Natural language patterns
    NL_PATTERNS = [
        (r'\b(please|could you|would you|can you|I need|help me)\b', 2.0),
        (r'\b(the|a|an|is|are|was|were|has|have|had)\b', 0.3),
        (r'[.!?]\s+[A-Z]', 0.5),    # Sentence boundaries
        (r'\b(however|therefore|furthermore|additionally|moreover)\b', 1.5),
        (r'\b(analyze|explain|summarize|describe|compare)\b', 1.0),
    ]

    # Threshold: if code_score / total_score > this, classify as code
    CODE_THRESHOLD = 0.55

    @classmethod
    def classify(cls, text: str) -> tuple[str, float]:
        """
        Classify text content type.
        
        Returns:
            (content_type, confidence) where content_type is 'nlc' or 'cac'
            and confidence is 0.0-1.0.
        """
        if not text or not text.strip():
            return 'nlc', 1.0

        code_score = 0.0
        nl_score = 0.0

        # Score code patterns
        for pattern, weight in cls.CODE_PATTERNS:
            matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
            code_score += len(matches) * weight

        # Score NL patterns
        for pattern, weight in cls.NL_PATTERNS:
            matches = re.findall(pattern, text, re.MULTILINE | re.IGNORECASE)
            nl_score += len(matches) * weight

        total_score = code_score + nl_score
        if total_score == 0:
            return 'nlc', 0.5  # Default to NL if nothing detected

        code_ratio = code_score / total_score

        if code_ratio > cls.CODE_THRESHOLD:
            confidence = min(1.0, code_ratio)
            return 'cac', confidence
        else:
            confidence = min(1.0, 1.0 - code_ratio)
            return 'nlc', confidence

    @classmethod
    def is_stack_trace(cls, text: str) -> bool:
        """Detect if text is primarily a stack trace or error log."""
        trace_indicators = [
            r'Traceback \(most recent call last\)',
            r'^\s+at\s+\w+',
            r'^\s+File ".*", line \d+',
            r'Exception:|Error:',
            r'^\s+\d+\s+\|',  # Line-numbered output
        ]
        matches = sum(
            1 for p in trace_indicators
            if re.search(p, text, re.MULTILINE)
        )
        return matches >= 2

    @classmethod
    def is_log_dump(cls, text: str) -> bool:
        """Detect if text is a log dump."""
        lines = text.strip().split('\n')
        if len(lines) < 5:
            return False
        
        log_pattern = re.compile(
            r'^\d{4}[-/]\d{2}[-/]\d{2}|'
            r'^(WARN|INFO|DEBUG|ERROR|FATAL|TRACE)\s|'
            r'^\[\d{4}[-/]\d{2}[-/]\d{2}'
        )
        log_lines = sum(1 for line in lines if log_pattern.match(line.strip()))
        return log_lines / len(lines) > 0.4
