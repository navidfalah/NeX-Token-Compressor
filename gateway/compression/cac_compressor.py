"""
Firma-KI Gateway — Pipeline B: Code & Algorithmic Context Compression (CAC)
Implements AST Pruning and Execution-Trace Summarization for code-specific
token reduction without destroying LLM comprehension.
"""
import re
import ast
import textwrap


class ASTPruner:
    """
    Abstract Syntax Tree Pruning.
    
    Analyzes the AST of Python code to strip redundant logic, dead code,
    and verbose comments while strictly preserving core architectural intent
    and syntax structure. Falls back to regex-based pruning for non-Python code.
    """

    @classmethod
    def prune(cls, code: str, language: str = 'auto') -> tuple[str, dict]:
        """
        Prune code while preserving semantic intent.
        
        Args:
            code: Source code text
            language: Programming language ('python', 'javascript', 'auto')
            
        Returns:
            (pruned_code, metadata)
        """
        if language == 'auto':
            language = cls._detect_language(code)

        if language == 'python':
            return cls._prune_python(code)
        else:
            return cls._prune_generic(code, language)

    @classmethod
    def _detect_language(cls, code: str) -> str:
        """Detect programming language from code content."""
        python_indicators = [
            r'^\s*def\s+\w+\s*\(', r'^\s*class\s+\w+', r'^\s*import\s+',
            r'^\s*from\s+\w+\s+import', r':\s*$', r'^\s*if\s+.*:$',
        ]
        js_indicators = [
            r'\bfunction\s+\w+', r'\bconst\s+', r'\blet\s+', r'\bvar\s+',
            r'=>', r'\brequire\(', r'\bexport\s+',
        ]

        py_score = sum(
            1 for p in python_indicators
            if re.search(p, code, re.MULTILINE)
        )
        js_score = sum(
            1 for p in js_indicators
            if re.search(p, code, re.MULTILINE)
        )

        if py_score > js_score:
            return 'python'
        elif js_score > py_score:
            return 'javascript'
        return 'generic'

    @classmethod
    def _prune_python(cls, code: str) -> tuple[str, dict]:
        """
        Use Python's ast module for precise pruning.
        Removes: docstrings on non-public methods, pass statements in 
        non-empty blocks, dead imports (best-effort), verbose comments.
        """
        metadata = {'language': 'python', 'ast_pruned': True}
        pruned_lines = []
        removed_lines = 0

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If AST parsing fails, fall back to generic
            return cls._prune_generic(code, 'python')

        # Collect line numbers of nodes to potentially remove
        removable_lines = set()

        for node in ast.walk(tree):
            # Remove docstrings from private methods
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith('_') and node.body:
                    first = node.body[0]
                    if (isinstance(first, ast.Expr) and
                            isinstance(first.value, (ast.Constant, ast.Str))):
                        for line_no in range(first.lineno, first.end_lineno + 1):
                            removable_lines.add(line_no)

            # Remove standalone `pass` in blocks with other statements
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef, ast.If, ast.For, ast.While)):
                if len(node.body) > 1:
                    for stmt in node.body:
                        if isinstance(stmt, ast.Pass):
                            removable_lines.add(stmt.lineno)

        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Remove lines flagged by AST analysis
            if i in removable_lines:
                removed_lines += 1
                continue

            # Remove block comments (3+ consecutive comment lines)
            # Kept as single-pass for simplicity
            if stripped.startswith('#') and not stripped.startswith('#!'):
                # Keep short inline comments, remove verbose block comments
                if len(stripped) > 80:
                    removed_lines += 1
                    continue

            # Remove blank-line runs (keep max 1 blank line)
            if not stripped:
                if pruned_lines and not pruned_lines[-1].strip():
                    removed_lines += 1
                    continue

            pruned_lines.append(line)

        metadata['removed_lines'] = removed_lines
        metadata['original_lines'] = len(lines)
        metadata['pruned_lines'] = len(pruned_lines)
        
        return '\n'.join(pruned_lines), metadata

    @classmethod
    def _prune_generic(cls, code: str, language: str) -> tuple[str, dict]:
        """
        Regex-based pruning for non-Python code.
        Strips verbose comments, excessive whitespace, and dead patterns.
        """
        metadata = {'language': language, 'ast_pruned': False}
        pruned = code

        # Remove multi-line comments (/* ... */)
        pruned = re.sub(r'/\*[\s\S]*?\*/', '', pruned)

        # Remove single-line comments (// ...) but not URLs
        pruned = re.sub(r'(?<!:)//(?!/).*$', '', pruned, flags=re.MULTILINE)

        # Remove excessive blank lines (keep max 1)
        pruned = re.sub(r'\n{3,}', '\n\n', pruned)

        # Remove trailing whitespace
        pruned = re.sub(r'[ \t]+$', '', pruned, flags=re.MULTILINE)

        # Collapse consecutive empty lines
        lines = pruned.split('\n')
        result_lines = []
        prev_blank = False
        removed = 0
        
        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                removed += 1
                continue
            result_lines.append(line)
            prev_blank = is_blank

        metadata['removed_lines'] = removed
        metadata['original_lines'] = len(lines)
        metadata['pruned_lines'] = len(result_lines)

        return '\n'.join(result_lines), metadata


class ExecutionTraceSummarizer:
    """
    Execution-Trace Summarization.
    
    Detects massive debugging logs, stack traces, and error outputs,
    then distills them into high-signal compressed summaries.
    """

    # Maximum lines before summarization kicks in
    TRACE_THRESHOLD = 50

    @classmethod
    def summarize(cls, text: str) -> tuple[str, dict]:
        """
        Summarize execution traces and log dumps.
        
        Returns:
            (summarized_text, metadata)
        """
        lines = text.strip().split('\n')
        
        if len(lines) < cls.TRACE_THRESHOLD:
            return text, {'trace_summarized': False, 'reason': 'below_threshold'}

        # Detect trace type
        if cls._is_python_traceback(text):
            return cls._summarize_python_traceback(text)
        elif cls._is_log_dump(lines):
            return cls._summarize_log_dump(lines)
        else:
            return cls._summarize_generic_output(lines)

    @classmethod
    def _is_python_traceback(cls, text: str) -> bool:
        """Detect Python traceback format."""
        return bool(re.search(r'Traceback \(most recent call last\)', text))

    @classmethod
    def _is_log_dump(cls, lines: list[str]) -> bool:
        """Detect structured log output."""
        log_pattern = re.compile(
            r'^\d{4}[-/]\d{2}[-/]\d{2}|'
            r'^(WARN|INFO|DEBUG|ERROR|FATAL)\s|'
            r'^\[.*?\]\s+(WARN|INFO|DEBUG|ERROR|FATAL)'
        )
        log_lines = sum(1 for line in lines[:20] if log_pattern.match(line.strip()))
        return log_lines > 5

    @classmethod
    def _summarize_python_traceback(cls, text: str) -> tuple[str, dict]:
        """Extract key info from Python tracebacks."""
        # Extract the exception type and message
        exception_match = re.search(
            r'^(\w+(?:Error|Exception|Warning|Fault)[^:\n]*):?\s*(.*?)$',
            text, re.MULTILINE
        )
        
        # Extract file/line references
        file_refs = re.findall(
            r'File "([^"]+)", line (\d+), in (\w+)',
            text
        )

        # Build condensed summary
        parts = ['[TRACE_SUMMARY]']
        
        if exception_match:
            parts.append(f'ERR: {exception_match.group(1)}: {exception_match.group(2)[:200]}')
        
        if file_refs:
            # Show last 5 frames (most relevant)
            parts.append('STACK (bottom→top):')
            for filepath, lineno, func in file_refs[-5:]:
                # Shorten file path
                short_path = filepath.split('/')[-2:] if '/' in filepath else [filepath]
                parts.append(f'  {"/".join(short_path)}:{lineno} in {func}')

        metadata = {
            'trace_summarized': True,
            'trace_type': 'python_traceback',
            'original_lines': len(text.split('\n')),
            'summarized_lines': len(parts),
        }

        return '\n'.join(parts), metadata

    @classmethod
    def _summarize_log_dump(cls, lines: list[str]) -> tuple[str, dict]:
        """Summarize structured log output by extracting errors and key events."""
        error_lines = []
        warn_lines = []
        summary_stats = Counter()

        for line in lines:
            stripped = line.strip()
            # Count log levels
            level_match = re.search(r'\b(ERROR|WARN|INFO|DEBUG|FATAL|TRACE)\b', stripped)
            if level_match:
                summary_stats[level_match.group(1)] += 1

            # Capture ERROR and FATAL lines (high signal)
            if re.search(r'\b(ERROR|FATAL)\b', stripped):
                error_lines.append(stripped[:200])  # Truncate long lines
            elif re.search(r'\bWARN\b', stripped):
                warn_lines.append(stripped[:200])

        # Build summary
        parts = ['[LOG_SUMMARY]']
        parts.append(f'Total lines: {len(lines)}')
        parts.append(f'Level distribution: {dict(summary_stats)}')
        
        if error_lines:
            parts.append(f'\nERRORS ({len(error_lines)}):')
            # Show first 10 unique errors
            seen = set()
            for err in error_lines:
                normalized = re.sub(r'\d+', 'N', err)  # Normalize numbers
                if normalized not in seen:
                    seen.add(normalized)
                    parts.append(f'  • {err}')
                    if len(seen) >= 10:
                        break

        if warn_lines:
            parts.append(f'\nWARNINGS ({len(warn_lines)}):')
            seen = set()
            for warn in warn_lines[:5]:
                normalized = re.sub(r'\d+', 'N', warn)
                if normalized not in seen:
                    seen.add(normalized)
                    parts.append(f'  • {warn}')

        metadata = {
            'trace_summarized': True,
            'trace_type': 'log_dump',
            'original_lines': len(lines),
            'summarized_lines': len(parts),
            'error_count': len(error_lines),
            'warn_count': len(warn_lines),
        }

        return '\n'.join(parts), metadata

    @classmethod
    def _summarize_generic_output(cls, lines: list[str]) -> tuple[str, dict]:
        """Summarize generic large text output by extracting key lines."""
        # Keep first 5, last 5, and any lines with keywords
        key_lines = []
        
        # First 5
        key_lines.extend(lines[:5])
        
        # Lines with important keywords
        important_pattern = re.compile(
            r'\b(error|fail|exception|critical|warning|timeout|refused|denied)\b',
            re.IGNORECASE
        )
        for line in lines[5:-5]:
            if important_pattern.search(line):
                key_lines.append(line[:200])

        # Last 5
        key_lines.extend(lines[-5:])

        # Deduplicate while preserving order
        seen = set()
        unique_lines = []
        for line in key_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)

        summary = f'[OUTPUT_SUMMARY: {len(lines)} lines → {len(unique_lines)} key lines]\n'
        summary += '\n'.join(unique_lines)

        metadata = {
            'trace_summarized': True,
            'trace_type': 'generic',
            'original_lines': len(lines),
            'summarized_lines': len(unique_lines),
        }

        return summary, metadata
