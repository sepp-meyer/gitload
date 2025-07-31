# app/analyzer.py
"""
Sammlung von Analyzer-Klassen.
Jede Klasse liefert
    1) eine flache Liste von Dicts  → Tabellenansicht
    2) eine Baum-Struktur           → Codebaum-Ansicht
"""

from __future__ import annotations
from pathlib import Path
import ast
import re
from collections import defaultdict
from typing import List, Dict


class BaseAnalyzer:
    # ---- Tabellen-Analyse ----------------------------------------
    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        return []

    # ---- Baum-Analyse --------------------------------------------
    def analyse_tree(self, rel_path: str, text: str) -> Dict:
        return {}


# ───────── Python ────────────────────────────────────────────────
class PythonAnalyzer(BaseAnalyzer):
    """Analysiert .py-Dateien (Funktionen, Routen, Funktions-Calls, Imports)"""

    # ------------------------------------------------ Tabelle ------
    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []

        rows: List[Dict] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rows.append({
                    "file":   rel_path,
                    "func":   node.name,
                    "route":  self._extract_route(node.decorator_list),
                    "class":  self._enclosing_class(node),
                    "lineno": node.lineno,
                })
        return rows

    # ------------------------------------------------ Baum ---------
    def analyse_tree(self, rel_path: str, text: str) -> Dict:
        """
        Gibt ein Dict mit
            - functions  → Routen + Aufrufe
            - imports    → Liste aller Import-Statements
        zurück.
        """
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {}

        # Parent-Links für Klassenermittlung
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child.parent = parent

        out: Dict = {
            "functions": {},
            "imports":   self._collect_imports(tree),
        }

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            meta = {
                "route": self._extract_route(node.decorator_list),
                "calls": self._collect_calls(node),
            }
            out["functions"][node.name] = meta

        return out

    # --------------------------------------------- Hilfsmethoden --
    def _extract_route(self, decorators):
        """Sucht @bp.route('/xyz')-Dekoratoren."""
        for dec in decorators:
            if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                for arg in dec.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        return arg.value
        return ""

    def _collect_calls(self, func_node):
        """Sammelt alle Funktions-/Methoden-Aufrufe innerhalb einer Funktion."""
        called = set()
        for sub in ast.walk(func_node):
            if isinstance(sub, ast.Call):
                tgt = sub.func
                if isinstance(tgt, ast.Name):
                    called.add(tgt.id)
                elif isinstance(tgt, ast.Attribute):
                    called.add(tgt.attr)
        return sorted(called)

    def _collect_imports(self, tree: ast.AST) -> List[Dict]:
        """Extrahiert alle Import-Anweisungen aus der Datei."""
        imps: List[Dict] = []
        for node in ast.walk(tree):
            # import xyz as ab
            if isinstance(node, ast.Import):
                for n in node.names:
                    imps.append({
                        "type":   "import",
                        "module": n.name,
                        "name":   None,
                        "alias":  n.asname,
                        "lineno": node.lineno,
                    })
            # from pkg.mod import foo as bar
            elif isinstance(node, ast.ImportFrom):
                base_mod = "." * node.level + (node.module or "")
                for n in node.names:
                    imps.append({
                        "type":   "from",
                        "module": base_mod,
                        "name":   n.name,
                        "alias":  n.asname,
                        "lineno": node.lineno,
                    })
        return imps

    def _enclosing_class(self, node):
        p = getattr(node, "parent", None)
        while p:
            if isinstance(p, ast.ClassDef):
                return p.name
            p = getattr(p, "parent", None)
        return ""


# ───────── CSS  (Selektoren → Funktion) ──────────────────────────
class CSSAnalyzer(BaseAnalyzer):
    _sel = re.compile(r"^\s*([^{]+?)\s*\{", re.MULTILINE)

    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        return [
            {"file": rel_path, "func": m.group(1).strip()}
            for m in self._sel.finditer(text)
        ]
    # CSS-Dateien bekommen keinen Codebaum


# ───────── Mapping / Registry ────────────────────────────────────
REGISTRY = defaultdict(BaseAnalyzer)
REGISTRY.update({
    ".py": PythonAnalyzer(),
    # ".css": CSSAnalyzer(),   # bei Bedarf aktivieren
})
