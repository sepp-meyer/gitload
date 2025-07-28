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
# app/analyzer.py
class PythonAnalyzer(BaseAnalyzer):
    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []

        rows: List[Dict] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            # ───── Grunddaten ───────────────────────────────
            entry = {
                "file":    rel_path,
                "func":    node.name,
                "route":   "",          # wird evtl. gefüllt
                "class":   self._enclosing_class(node),
                "lineno":  node.lineno,
            }

            # ───── Decorators untersuchen (Flask‑Routen) ────
            for dec in node.decorator_list:
                # Fälle: @bp.route("/x"), @app.route("/x", ...)
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                    # Erste Positional‑Args einsammeln (können mehrere sein)
                    paths = []
                    for arg in dec.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            paths.append(arg.value)
                    entry["route"] = ", ".join(paths)
                    break   # reicht, wir nehmen nur die erste Route

            rows.append(entry)

        return rows

    # ───────────────────────────────────────────────────────
    def _enclosing_class(self, node: ast.AST) -> str:
        """Falls die Funktion innerhalb einer Klasse liegt, gebe Klassennamen zurück."""
        parent = getattr(node, "parent", None)
        while parent:
            if isinstance(parent, ast.ClassDef):
                return parent.name
            parent = getattr(parent, "parent", None)
        return ""



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
    ".py": PythonAnalyzer(),
    # ".css": CSSAnalyzer(),   # vorerst auskommentiert
    # später: ".js": JsAnalyzer(), ".html": HtmlAnalyzer(), …
})

