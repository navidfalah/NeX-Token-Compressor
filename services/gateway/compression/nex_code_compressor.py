"""
Firma-KI Gateway — NEX Code Compression Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Deterministic, lossless-where-critical compression for SOURCE CODE payloads.

Levels
──────
  🟢 LIGHT    — Safe, reversible; removes obvious redundancy. ~10-25% savings
  🟡 MEDIUM   — Structural compression; AST-level pruning.   ~25-50% savings
  🟠 AGGRESSIVE — Deep minification; identifier rewriting.   ~50-70% savings
  🔴 EXTREME  — NEX bytecode transpilation (machine-native). ~70-85% savings
"""

from __future__ import annotations

import ast
import re
import hashlib
import dataclasses
from typing import Optional


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


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

class WhitespaceCompactor:
    """🟢 LIGHT — Collapse blank lines, trailing spaces. ~5% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        lines = [l.rstrip() for l in source.split('\n')]
        result: list[str] = []
        prev_blank = False
        for line in lines:
            blank = line.strip() == ''
            if blank and prev_blank:
                continue
            result.append(line)
            prev_blank = blank
        out = '\n'.join(result).strip()
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


class ImportDeduplicator:
    """🟢 LIGHT — Remove duplicate import statements. ~2% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        lines = source.split('\n')
        seen: set[str] = set()
        result: list[str] = []
        for line in lines:
            key = line.strip()
            if key.startswith(('import ', 'from ')):
                if key in seen:
                    continue
                seen.add(key)
            result.append(line)
        out = '\n'.join(result)
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


class MarkdownCodeFenceStripper:
    """🟢 LIGHT — Remove ``` code fences from AI-generated responses."""
    _FENCE = re.compile(r'^```[\w]*\n?([\s\S]*?)```\s*$', re.MULTILINE)

    @classmethod
    def apply(cls, text: str) -> tuple[str, int]:
        match = cls._FENCE.search(text)
        if match:
            out = match.group(1).strip()
            return out, max(0, _estimate_tokens(text) - _estimate_tokens(out))
        return text, 0


# ═══════════════════════════════════════════════════════════════════════════════
#  🟡 MEDIUM ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class CommentPruner:
    """🟡 MEDIUM — Multi-language comment removal (#, //, /* */, HTML, SQL). ~15% savings."""
    _RULES = [
        (re.compile(r'#[^\n]*', re.MULTILINE), ''),
        (re.compile(r'//[^\n]*', re.MULTILINE), ''),
        (re.compile(r'/\*[\s\S]*?\*/', re.DOTALL), ''),
        (re.compile(r'--[^\n]*', re.MULTILINE), ''),
        (re.compile(r'<!--[\s\S]*?-->', re.DOTALL), ''),
        (re.compile(r'"""[\s\S]*?"""', re.DOTALL), ''),
        (re.compile(r"'''[\s\S]*?'''", re.DOTALL), ''),
        (re.compile(r'\n\s*\n+'), '\n'),
    ]

    @classmethod
    def apply(cls, source: str) -> tuple[str, int]:
        r = source
        for pattern, repl in cls._RULES:
            r = pattern.sub(repl, r)
        return r.strip(), max(0, _estimate_tokens(source) - _estimate_tokens(r))


class TypeAnnotationEraser:
    """🟡 MEDIUM — Remove Python type annotations; AI doesn't need them. ~10% savings."""
    _RETURN_ANN = re.compile(r'\)\s*->\s*[\w\[\], |."\']+\s*(?=:)', re.MULTILINE)
    _PARAM_ANN  = re.compile(r'(\w+)\s*:\s*[\w\[\], |."\']+\s*(?=[,)=])', re.MULTILINE)

    @classmethod
    def apply(cls, source: str) -> tuple[str, int]:
        r = cls._RETURN_ANN.sub(')', source)
        r = cls._PARAM_ANN.sub(r'\1', r)
        r = re.sub(r'\n\s*\n+', '\n', r)
        return r, max(0, _estimate_tokens(source) - _estimate_tokens(r))


class DeadCodeEliminator:
    """🟡 MEDIUM — Remove unreachable code after return/raise/break. ~8% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        lines = source.split('\n')
        result: list[str] = []
        skip_to_indent: Optional[int] = None
        for line in lines:
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            if skip_to_indent is not None:
                if current_indent > skip_to_indent or stripped == '':
                    continue
                else:
                    skip_to_indent = None
            if stripped == 'pass':
                continue
            result.append(line)
            if re.match(r'^\s*(return|raise|break|continue)\b', line):
                skip_to_indent = current_indent
        out = '\n'.join(result)
        out = re.sub(r'\n\s*\n+', '\n', out).strip()
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


class StructuralDuplicateEliminator:
    """🟡 MEDIUM — Hash-based detection and removal of duplicate code blocks. ~12% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        """Split into logical blocks (classes/functions) and remove hash-identical duplicates."""
        # Split on function/class boundaries
        block_pattern = re.compile(r'^((?:async\s+)?def\s+\w+|class\s+\w+)', re.MULTILINE)
        positions = [m.start() for m in block_pattern.finditer(source)]
        if len(positions) < 2:
            return source, 0

        blocks: list[str] = []
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(source) else len(source)
            blocks.append(source[pos:end])

        header = source[:positions[0]] if positions else ''
        seen_hashes: set[str] = set()
        unique_blocks: list[str] = []
        for block in blocks:
            try:
                # Upgraded: Parameterized Deduplication
                # We hash the AST structure but strip all literals (Constants) and names
                tree = ast.parse(block)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant):
                        node.value = None
                    if isinstance(node, ast.Name):
                        node.id = "_"
                struct_hash = hashlib.md5(ast.dump(tree).encode()).hexdigest()
            except Exception:
                struct_hash = hashlib.md5(block.encode()).hexdigest()

            if struct_hash not in seen_hashes:
                seen_hashes.add(struct_hash)
                unique_blocks.append(block)

        out = header + '\n'.join(unique_blocks)
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🟠 AGGRESSIVE ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class PythonASTStripper:
    """🟠 AGGRESSIVE — Parse Python → AST → unparse; drops all docstrings, dead expressions. ~30% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, 0

        class _Eraser(ast.NodeTransformer):
            def visit_Expr(self, node: ast.Expr):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return None
                return node
            
            def visit_FunctionDef(self, node):
                return self.generic_visit(node)
                
            visit_AsyncFunctionDef = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef

        tree = _Eraser().visit(tree)
        ast.fix_missing_locations(tree)
        try:
            result = ast.unparse(tree)
        except Exception:
            return source, 0
        return result, max(0, _estimate_tokens(source) - _estimate_tokens(result))


class IdentifierMinifier:
    """🟠 AGGRESSIVE — Rename local variables to single chars (a,b,c…) for maximum density. ~25% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        """Rename local variables in Python functions to minimal identifiers."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source, 0

        _BUILTINS = frozenset({
            'print', 'len', 'range', 'str', 'int', 'float', 'list', 'dict',
            'set', 'tuple', 'bool', 'None', 'True', 'False', 'self', 'cls',
            'type', 'isinstance', 'hasattr', 'getattr', 'setattr', 'open',
            'enumerate', 'zip', 'map', 'filter', 'sorted', 'reversed',
            'sum', 'min', 'max', 'abs', 'round', 'super', 'object',
            'Exception', 'return', 'yield', 'import', 'from', 'as',
        })
        _CHARS = 'abcdefghijklmnopqrstuvwxyz'

        def _short_name(i: int) -> str:
            if i < 26:
                return _CHARS[i]
            return _CHARS[i // 26 - 1] + _CHARS[i % 26]

        class _Minifier(ast.NodeTransformer):
            def __init__(self):
                self._counter = 0
                self._map: dict[str, str] = {}

            def _rename(self, name: str) -> str:
                if name in _BUILTINS or name.startswith('__'):
                    return name
                if name not in self._map:
                    self._map[name] = _short_name(self._counter)
                    self._counter += 1
                return self._map[name]

            def visit_FunctionDef(self, node):
                node.name = self._rename(node.name)
                # Rename params
                for a in node.args.args:
                    if a.arg != 'self':
                        a.arg = self._rename(a.arg)
                node.body = [self.visit(s) for s in node.body]
                return node

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node):
                node.name = self._rename(node.name)
                node.body = [self.visit(s) for s in node.body]
                return node

            def visit_Name(self, node):
                if isinstance(node.ctx, (ast.Store, ast.Load, ast.Param)):
                    node.id = self._rename(node.id)
                return node

            def visit_Attribute(self, node):
                # Optionally rename attributes if they aren't part of a known library?
                # For now, keep it simple/safe.
                node.value = self.visit(node.value)
                return node

        try:
            new_tree = _Minifier().visit(tree)
            ast.fix_missing_locations(new_tree)
            out = ast.unparse(new_tree)
            return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))
        except Exception:
            return source, 0


class LogicFlattener:
    """🟠 AGGRESSIVE — Inline single-assignment variables; collapse trivial wrappers. ~15% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        """Remove `x = expr; return x` patterns → `return expr`."""
        # Pattern: variable assigned once and immediately returned
        pattern = re.compile(
            r'(\s+)(\w+)\s*=\s*(.+)\n\1return\s+\2\b',
            re.MULTILINE
        )
        out = pattern.sub(r'\1return \3', source)
        # Also remove: x = expr; yield x → yield expr
        out = re.compile(
            r'(\s+)(\w+)\s*=\s*(.+)\n\1yield\s+\2\b',
            re.MULTILINE
        ).sub(r'\1yield \3', out)
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  🔴 EXTREME ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class NEXBytecodeTranspiler:
    """🔴 EXTREME — Transpile code structure to NEX bracket notation. ~65% savings."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        """Convert code to NEX notation using structural pattern matching."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return NEXBytecodeTranspiler._regex_transpile(source)

        parts: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = ','.join(a.arg for a in node.args.args if a.arg != 'self')
                parts.append(f'[FN:{node.name}({args})]')
            elif isinstance(node, ast.ClassDef):
                bases = ','.join(ast.unparse(b) for b in node.bases)
                parts.append(f'[CLS:{node.name}<{bases}>]')
            elif isinstance(node, ast.Import):
                names = ','.join(alias.name for alias in node.names)
                parts.append(f'[IMP:{names}]')
            elif isinstance(node, ast.ImportFrom):
                names = ','.join(alias.name for alias in node.names)
                parts.append(f'[IMP:{node.module}.{{{names}}}]')
            elif isinstance(node, ast.If):
                parts.append(f'[IF:{ast.unparse(node.test)}]')
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                cond = ast.unparse(node.target) + 'IN' + ast.unparse(node.iter) if isinstance(node, (ast.For, ast.AsyncFor)) else ast.unparse(node.test)
                parts.append(f'[LOOP:{cond}]')
            elif isinstance(node, ast.Try):
                parts.append('[TRY]')
            elif isinstance(node, ast.With):
                parts.append(f'[WITH:{",".join(ast.unparse(i.context_expr) for i in node.items)}]')
            elif isinstance(node, ast.Return) and node.value:
                parts.append(f'[RET:{ast.unparse(node.value)}]')
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    parts.append(f'[SET:{ast.unparse(target)}={ast.unparse(node.value)}]')
            elif isinstance(node, ast.Raise) and node.exc:
                parts.append(f'[RAISE:{ast.unparse(node.exc)}]')
            elif isinstance(node, ast.Call):
                parts.append(f'[CALL:{ast.unparse(node.func)}]')

        out = ' '.join(parts) if parts else source
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))

    @staticmethod
    def _regex_transpile(source: str) -> tuple[str, int]:
        """Fallback regex-based transpilation for non-Python."""
        out = source
        out = re.sub(r'function\s+(\w+)\s*\(([^)]*)\)\s*\{', r'[FN:\1(\2)]', out)
        out = re.sub(r'class\s+(\w+)', r'[CLS:\1]', out)
        out = re.sub(r'import\s+(.+?)\s*;?$', r'[IMP:\1]', out, flags=re.MULTILINE)
        out = re.sub(r'//[^\n]*', '', out)
        out = re.sub(r'\s+', ' ', out).strip()
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  OUTPUT-SIDE ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════════════

class TrailingCommentStripper:
    """🟢 LIGHT — Strip AI-added end-of-line explanatory comments."""
    _INLINE_COMMENT = re.compile(r'\s+#[^\n]*', re.MULTILINE)

    @classmethod
    def apply(cls, source: str) -> tuple[str, int]:
        out = cls._INLINE_COMMENT.sub('', source)
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


class RedundantNewlineCollapser:
    """🟢 LIGHT — Collapse 3+ consecutive blank lines to one."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        out = re.sub(r'\n{3,}', '\n\n', source).strip()
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


class OutputWhitespaceNormalizer:
    """🟢 LIGHT — Tabs→4 spaces, strip trailing spaces, one trailing newline."""
    @staticmethod
    def apply(source: str) -> tuple[str, int]:
        lines = source.expandtabs(4).split('\n')
        out = '\n'.join(l.rstrip() for l in lines).strip() + '\n'
        return out, max(0, _estimate_tokens(source) - _estimate_tokens(out))


# ═══════════════════════════════════════════════════════════════════════════════
#  ALGORITHM REGISTRY  (for the UI)
# ═══════════════════════════════════════════════════════════════════════════════

ALGO_REGISTRY = {
    # Input algorithms
    "whitespace":     {"name": "Whitespace Compact",        "level": "light",      "emoji": "🟢", "color": "#4ade80",  "savings": "~5%",  "desc": "Collapse blank lines and trailing spaces.", "fn": WhitespaceCompactor.apply,        "side": "input"},
    "import_dedup":   {"name": "Import Deduplicator",       "level": "light",      "emoji": "🟢", "color": "#4ade80",  "savings": "~2%",  "desc": "Remove duplicate import statements.",       "fn": ImportDeduplicator.apply,         "side": "input"},
    "comment_prune":  {"name": "Comment Pruner",            "level": "medium",     "emoji": "🟡", "color": "#fbbf24",  "savings": "~15%", "desc": "Strip #, //, /* */, SQL -- comments.",      "fn": CommentPruner.apply,              "side": "input"},
    "type_erase":     {"name": "Type Annotation Erase",     "level": "medium",     "emoji": "🟡", "color": "#fbbf24",  "savings": "~10%", "desc": "Remove Python type hints (→ type:).",       "fn": TypeAnnotationEraser.apply,       "side": "input"},
    "dead_code":      {"name": "Dead Code Eliminator",      "level": "medium",     "emoji": "🟡", "color": "#fbbf24",  "savings": "~8%",  "desc": "Remove unreachable code after return/raise.","fn": DeadCodeEliminator.apply,         "side": "input"},
    "struct_dedup":   {"name": "Structural Deduplicator",   "level": "medium",     "emoji": "🟡", "color": "#fbbf24",  "savings": "~12%", "desc": "Hash-based duplicate code block removal.",  "fn": StructuralDuplicateEliminator.apply, "side": "input"},
    "ast_strip":      {"name": "Python AST Prune",          "level": "aggressive", "emoji": "🟠", "color": "#fb923c",  "savings": "~30%", "desc": "Deep AST-level docstring + expr removal.",  "fn": PythonASTStripper.apply,          "side": "input"},
    "id_minify":      {"name": "Identifier Minifier",       "level": "aggressive", "emoji": "🟠", "color": "#fb923c",  "savings": "~25%", "desc": "Rename local vars to single chars (a,b,c).", "fn": IdentifierMinifier.apply,         "side": "input"},
    "logic_flatten":  {"name": "Logic Flattener",           "level": "aggressive", "emoji": "🟠", "color": "#fb923c",  "savings": "~15%", "desc": "Inline temp vars: x=expr;return x → return expr.", "fn": LogicFlattener.apply,       "side": "input"},
    "nex_transpile":  {"name": "NEX Bytecode Transpiler",   "level": "extreme",    "emoji": "🔴", "color": "#f87171",  "savings": "~65%", "desc": "Convert to NEX [FN:][CLS:] bracket notation.", "fn": NEXBytecodeTranspiler.apply,    "side": "input"},
    # Output algorithms
    "trailing_strip": {"name": "Trailing Comment Strip",    "level": "light",      "emoji": "🟢", "color": "#4ade80",  "savings": "~5%",  "desc": "Remove AI end-of-line explanatory comments.", "fn": TrailingCommentStripper.apply,    "side": "output"},
    "newline_collapse":{"name":"Redundant Newline Collapse", "level": "light",      "emoji": "🟢", "color": "#4ade80",  "savings": "~3%",  "desc": "Collapse 3+ blank lines → one.",            "fn": RedundantNewlineCollapser.apply,  "side": "output"},
    "ws_normalize":   {"name": "Whitespace Normalize",      "level": "light",      "emoji": "🟢", "color": "#4ade80",  "savings": "~2%",  "desc": "Tabs→spaces, trim trailing whitespace.",     "fn": OutputWhitespaceNormalizer.apply, "side": "output"},
}


# ═══════════════════════════════════════════════════════════════════════════════
#  PRESET PIPELINES
# ═══════════════════════════════════════════════════════════════════════════════

class NEXCodeCompressor:
    """
    Orchestrates code compression pipelines at different intensity levels.
    """

    # Standard production pipeline (INPUT)
    INPUT_PIPELINE = [
        ("PythonASTPrune",               PythonASTStripper.apply),
        ("TypeAnnotationErase",          TypeAnnotationEraser.apply),
        ("CommentPrune",                 CommentPruner.apply),
        ("DeadCodeEliminate",            DeadCodeEliminator.apply),
        ("StructuralDeduplicate",        StructuralDuplicateEliminator.apply),
        ("LogicFlatten",                 LogicFlattener.apply),
        ("ImportDeduplicate",            ImportDeduplicator.apply),
        ("WhitespaceCompact",            WhitespaceCompactor.apply),
    ]

    # NEX Extreme pipeline — terminates in bytecode
    INPUT_PIPELINE_EXTREME = [
        ("PythonASTPrune",               PythonASTStripper.apply),
        ("CommentPrune",                 CommentPruner.apply),
        ("IdentifierMinify",             IdentifierMinifier.apply),
        ("NEXBytecodeTranspile",         NEXBytecodeTranspiler.apply),
    ]

    OUTPUT_PIPELINE = [
        ("TrailingCommentStrip",         TrailingCommentStripper.apply),
        ("RedundantNewlineCollapse",     RedundantNewlineCollapser.apply),
        ("OutputWhitespaceNorm",         OutputWhitespaceNormalizer.apply),
    ]

    @classmethod
    def compress_input(cls, code: str, extreme: bool = False) -> CompressionResult:
        pipeline = cls.INPUT_PIPELINE_EXTREME if extreme else cls.INPUT_PIPELINE
        return cls._run(code, pipeline, "input")

    @classmethod
    def compress_output(cls, code: str) -> CompressionResult:
        return cls._run(code, cls.OUTPUT_PIPELINE, "output")

    @classmethod
    def compress_with_algo(cls, code: str, algo_key: str) -> CompressionResult:
        """Run a single named algorithm from the registry."""
        if algo_key not in ALGO_REGISTRY:
            return cls._run(code, [], "input")
        fn = ALGO_REGISTRY[algo_key]["fn"]
        tokens_before = _estimate_tokens(code)
        out, removed = fn(code)
        tokens_after = _estimate_tokens(out)
        savings_pct = round((tokens_before - tokens_after) / tokens_before * 100, 1) if tokens_before > 0 else 0.0
        return CompressionResult(
            compressed=out, original=code,
            tokens_before=tokens_before, tokens_after=tokens_after,
            savings_pct=savings_pct, pipeline_log=[(algo_key, removed)], side="input"
        )

    @classmethod
    def _run(cls, text: str, pipeline: list, side: str) -> CompressionResult:
        tokens_before = _estimate_tokens(text)
        log: list[tuple[str, int]] = []
        current = text
        for stage_name, fn in pipeline:
            current, removed = fn(current)
            log.append((stage_name, removed))
        tokens_after = _estimate_tokens(current)
        savings_pct = round((tokens_before - tokens_after) / tokens_before * 100, 1) if tokens_before > 0 else 0.0
        return CompressionResult(
            compressed=current, original=text,
            tokens_before=tokens_before, tokens_after=tokens_after,
            savings_pct=savings_pct, pipeline_log=log, side=side,
        )
