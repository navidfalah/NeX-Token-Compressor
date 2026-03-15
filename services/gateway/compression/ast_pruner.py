import ast
import re

class ASTPruner:
    """
    Lightweight module to algorithmically prune source code.
    Strips docstrings, comments, and redundant formatting to reduce token count.
    """

    @staticmethod
    def prune_python(source_code: str) -> str:
        """Prunes Python source code using AST parsing."""
        try:
            tree = ast.parse(source_code)
            
            # Remove docstrings
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                    if (node.body and isinstance(node.body[0], ast.Expr) and 
                        isinstance(node.body[0].value, ast.Constant) and 
                        isinstance(node.body[0].value.value, str)):
                        node.body.pop(0)
                        
            # Unparse back to code (Python 3.9+)
            pruned_code = ast.unparse(tree)
            
            # Additional regex cleanup for extra whitespace
            pruned_code = re.sub(r'\n\s*\n', '\n', pruned_code).strip()
            return pruned_code
        except Exception:
            # Fallback to simple regex if AST parsing fails (e.g., snippet is incomplete)
            return ASTPruner.basic_cleanup(source_code)

    @staticmethod
    def basic_cleanup(text: str) -> str:
        """Generic cleanup using regex for non-Python or broken code."""
        # Strip single line comments
        text = re.sub(r'#.*', '', text)
        # Strip multi-line comments (rough approximation)
        text = re.sub(r'\'\'\'(.*?)\'\'\'', '', text, flags=re.DOTALL)
        text = re.sub(r'\"\"\"(.*?)\"\"\"', '', text, flags=re.DOTALL)
        # remove extra lines
        text = re.sub(r'\n\s*\n', '\n', text).strip()
        return text

    @classmethod
    def prune(cls, content: str, language: str = "python") -> str:
        """Main entry point for algorithmic compression."""
        if language.lower() == "python":
            return cls.prune_python(content)
        return cls.basic_cleanup(content)
