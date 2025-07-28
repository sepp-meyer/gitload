# app/analyzer.py
"""
Sammlung von Analyzer‑Klassen.
Jede Klasse liefert eine Liste von Dicts mit mind.:
    {file: str, element: str}
"""

from __future__ import annotations
from pathlib import Path
import ast, re
from collections import defaultdict
from typing import List, Dict


class BaseAnalyzer:
    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        """Default: nichts erkennen."""
        return []


# ───────── Python ────────────────────────────────────────────────────
class PythonAnalyzer(BaseAnalyzer):
    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []

        out: List[Dict] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append({"file": rel_path, "element": node.name})
        return out


# ───────── CSS  (Selektoren → „Funktion“) ────────────────────────────
class CSSAnalyzer(BaseAnalyzer):
    # alles links von {            (kein Super‑Parser, reicht hier)
    _sel = re.compile(r"^\s*([^{]+?)\s*\{", re.MULTILINE)

    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        return [
            {"file": rel_path, "element": m.group(1).strip()}
            for m in self._sel.finditer(text)
        ]


# ───────── Mapping / Registry ────────────────────────────────────────
REGISTRY = defaultdict(BaseAnalyzer)   # Fallback
REGISTRY.update({
    ".py":  PythonAnalyzer(),
    ".css": CSSAnalyzer(),
    # später: ".js": JsAnalyzer(), ".html": HtmlAnalyzer(), …
})
