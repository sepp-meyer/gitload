# app/analyzer.py
"""
Sammlung von Analyzer-Klassen.
Jede Klasse liefert
    1) eine flache Tabelle  → Funktionsübersicht
    2) eine Baum-Struktur   → Code-Baum für UML
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


# ═════════════════════════════════════════════════════════════════
#  Python-Analyzer
# ═════════════════════════════════════════════════════════════════
class PythonAnalyzer(BaseAnalyzer):
    """
    Analysiert .py-Dateien und liefert

        {
          "functions": { funcname: { "route":..., "calls": [...], "out_calls": [...] }, ... },
          "imports":   [...],
          "aliases":   {...},
          "nested":    { parent_func: [inner1, inner2, ...], ... }
        }
    """

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
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {}

        # Parent-Links für Klassenermittlung
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                child.parent = parent  # type: ignore

        # 1) Nested-Funktionen sammeln
        nested: Dict[str, List[str]] = defaultdict(list)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        nested[node.name].append(child.name)

        # 2) Funktionen und Metadaten aufbauen
        functions: Dict[str, Dict] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            functions[node.name] = {
                "route":    self._extract_route(node.decorator_list),
                "calls":    self._collect_calls(node),
                "out_calls": [],
            }

        return {
            "functions": functions,
            "imports":   self._collect_imports(tree),
            "aliases":   self._collect_aliases(tree),
            "nested":    nested,
        }

    # ------------------------------------------------ Alias-Analyse -
    def analyse_aliases(self, rel_path: str, text: str) -> List[Dict]:
        rows: List[Dict] = []
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return rows

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if alias.asname:
                        rows.append({
                            "file":   rel_path,
                            "lineno": node.lineno,
                            "module": module,
                            "name":   alias.name,
                            "alias":  alias.asname,
                        })
        return rows

    # -------------------------------- Hilfs-Methoden --------------
    def _extract_route(self, decorators):
        for dec in decorators:
            if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                for arg in dec.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        return arg.value
        return ""

    def _collect_calls(self, func_node):
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
        imps: List[Dict] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    imps.append({
                        "type":   "import",
                        "module": n.name,
                        "name":   None,
                        "alias":  n.asname,
                        "lineno": node.lineno,
                    })
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

    def _collect_aliases(self, tree: ast.AST) -> Dict[str, str]:
        aliases: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    asname = n.asname or n.name.split(".")[0]
                    aliases[asname] = n.name
            elif isinstance(node, ast.ImportFrom):
                base = "." * node.level + (node.module or "")
                for n in node.names:
                    asname = n.asname or n.name
                    aliases[asname] = f"{base}.{n.name}".lstrip(".")
        return aliases

    def _enclosing_class(self, node):
        p = getattr(node, "parent", None)
        while p:
            if isinstance(p, ast.ClassDef):
                return p.name
            p = getattr(p, "parent", None)
        return ""


class CSSAnalyzer(BaseAnalyzer):
    _sel = re.compile(r"^\s*([^\{]+?)\s*\{", re.MULTILINE)

    def analyse(self, rel_path: str, text: str) -> List[Dict]:
        return [
            {"file": rel_path, "func": m.group(1).strip()}
            for m in self._sel.finditer(text)
        ]


# ───────── Registry ──────────────────────────────────────────────
REGISTRY = defaultdict(BaseAnalyzer)
REGISTRY.update({
    ".py": PythonAnalyzer(),
    # ".css": CSSAnalyzer(),
})
