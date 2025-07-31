# ────────────────────────────────────────────────────────────────────────
# app/routes.py
from __future__ import annotations
from pathlib import Path
from flask import (
    Blueprint, render_template, redirect, url_for,
    session, request, flash
)
from typing import Dict, List, Union
from collections import defaultdict
from app.forms import ProjectForm
from app import utils
import re

bp = Blueprint("main", __name__)

# ───────────────────────────────────────────────────────────────────────
#  Plant-UML-Generator  (Files → verschachtelte Packages,
#                        Functions → Komponenten,
#                        Calls     → Funktions-Kanten)
# ───────────────────────────────────────────────────────────────────────
# aktualisierte build_package_uml mit trim im resolve_module
def build_package_uml(code_tree: Dict[str, dict]) -> str:
    # ── Hilfsfunktionen ──────────────────────────────────────────────
    def esc(s: str) -> str:
        """ersetzt alle Nicht-Word-Zeichen → valider UML-Alias"""
        return re.sub(r"[^A-Za-z0-9_]", "_", s)

    def trim(rel: str) -> str:
        """
        wirft das ZIP-Root weg:
            'sepp-meyer-gitload-…/app/routes.py' → 'app/routes.py'
        """
        
        parts = Path(rel).parts
        return "/".join(parts[1:]) if len(parts) > 1 else rel

    # ─────────────────────────────────────────────────────────────────
    # 0) Nested-Kinder global sammeln (damit wir sie im Baum ausblenden,
    #    aber weiterhin Calls/Kanten erzeugen können)
    # ─────────────────────────────────────────────────────────────────
    nested_children: set[str] = {
        inner
        for meta in code_tree.values()
        for inners in meta.get("nested", {}).values()
        for inner in inners
    }

    # ─────────────────────────────────────────────────────────────────
    # 1) Baum der Ordner / Dateien / Top-Level-Funktionen aufbauen
    # ─────────────────────────────────────────────────────────────────
    Tree = dict[str, "Tree | list[str]"]      # rekursiver Typ
    root: Tree = {}

    for rel, meta in code_tree.items():
        parts = Path(trim(rel)).parts
        ptr: Tree = root
        for folder in parts[:-1]:
            ptr = ptr.setdefault(folder, {})
        # nur Top-Level-Funktionen (nested-Kinder werden später als
        # Unter-Komponenten gerendert)
        top_funcs = [
            fn for fn in meta.get("functions", {})
            if fn not in nested_children
        ]
        ptr[parts[-1]] = top_funcs

    # ─────────────────────────────────────────────────────────────────
    # 2) UML-Text vorbereiten
    # ─────────────────────────────────────────────────────────────────
    lines: List[str] = [
        "@startuml",
        "left to right direction",
        'skinparam defaultFontName "Courier New"',
    ]

    # ✱ Lookup-Tabelle für schnellen Zugriff auf Nested-Infos
    trim2meta: Dict[str, Dict] = {trim(rel): meta for rel, meta in code_tree.items()}

    # ─────────────────────────────────────────────────────────────────
    # 3) Rekursives Rendern
    # ─────────────────────────────────────────────────────────────────
    def render(name: str,
               node: Union["Tree", list[str]],
               path_so_far: str,
               indent: str = "") -> None:

        alias = esc(path_so_far or name)
        lines.append(f'{indent}package "{name}" as {alias} {{')

        if isinstance(node, dict):
            # ── Unterordner / Dateien ───────────────────────────────
            for child, sub in sorted(node.items()):
                new_path = f"{path_so_far}/{child}" if path_so_far else child
                render(child, sub, new_path, indent + "  ")

        elif node:                   # Liste der Top-Level-Funktionen der Datei
            nested_map = trim2meta.get(path_so_far, {}).get("nested", {})

            # --------------------------------------------------------
            # rekursiv eine Funktion (und ihre Kinder) ausgeben
            # --------------------------------------------------------
            def render_fn(fn_name: str,
                          alias_prefix: str,
                          indent_fn: str) -> None:
                # alle direkten Kinder dieser Funktion
                children = nested_map.get(fn_name, [])

                cur_alias_prefix = f"{alias_prefix}__{fn_name}" \
                                   if alias_prefix else f"{path_so_far}__{fn_name}"
                cur_alias = esc(cur_alias_prefix)

                if children:                         # → eigenes Paket
                    lines.append(f'{indent_fn}package "{fn_name}()" as {cur_alias} {{')
                    next_indent = indent_fn + "  "
                    for child in sorted(children):
                        render_fn(child, cur_alias_prefix, next_indent)
                    lines.append(f'{indent_fn}}}')
                else:                               # → einfache Komponente
                    lines.append(f'{indent_fn}component "{fn_name}()" as {cur_alias}')

            # alle Top-Level-Funktionen der Datei abarbeiten
            for fn in sorted(node):
                render_fn(fn, "", indent + "  ")


        else:
            # Datei ohne Funktionen
            placeholder = esc(f"{path_so_far}__file")
            lines.append(f'{indent}  component "{name}" as {placeholder}')

        lines.append(f"{indent}}}")

    for top, sub in sorted(root.items()):
        render(top, sub, top)

    # ─────────────────────────────────────────────────────────────────
    # 4) Alias-Map für alle (!) Funktionen des Projekts
    # ─────────────────────────────────────────────────────────────────
    func2alias: Dict[str, str] = {}
    file_of_alias: Dict[str, str] = {}

    for rel, meta in code_tree.items():
        rel_trim = trim(rel)
        mod_alias = esc(rel_trim)

        # 4a) Top-Level-Funktionen
        for fn in meta.get("functions", {}):
            alias = esc(f"{rel_trim}__{fn}")
            func2alias[fn] = alias
            file_of_alias[alias] = mod_alias

        # 4b) **NEU → Nested-Funktionen**
        for parent, inners in meta.get("nested", {}).items():
            for inner in inners:
                alias = esc(f"{rel_trim}__{parent}__{inner}")   # 1
                func2alias[inner] = alias                        # 2
                file_of_alias[alias] = mod_alias                 # 3


    # ─────────────────────────────────────────────────────────────────
    # 5) Modul-Auflösung  (Import-Strings → Dateiname ohne Suffix)
    # ─────────────────────────────────────────────────────────────────
    def resolve_module(origin: str, raw: str) -> str:
        rel_trimmed = trim(origin)
        base = Path("/".join(rel_trimmed.split("/")[:-1]))  # Ordner d. Quelle
        level = len(raw) - len(raw.lstrip("."))
        name  = raw.lstrip(".")
        for _ in range(max(0, level - 1)):
            base = base.parent
        if name:
            for part in name.split("."):
                base = base / part
        return base.stem

    name2module: Dict[str, str] = {}
    for origin, meta in code_tree.items():
        for imp in meta.get("imports", []):
            canon = resolve_module(origin, imp["module"])
            if imp["type"] == "from":
                n = imp.get("alias") or imp.get("name")
                if n:
                    name2module[n] = canon
            else:
                alias = imp.get("alias") or imp["module"].split(".")[0]
                name2module[alias] = canon

    # ─────────────────────────────────────────────────────────────────
    # 6) Externe Funktionen sammeln
    # ─────────────────────────────────────────────────────────────────
    all_calls = {
        c
        for meta in code_tree.values()
        for fn_meta in meta.get("functions", {}).values()
        for c in fn_meta.get("calls", [])
    }
    external_fns = sorted(
        c for c in all_calls
        if c not in func2alias and c in name2module
    )
    for fn in external_fns:
        func2alias[fn] = esc(f"extern__{fn}")

    # ─────────────────────────────────────────────────────────────────
    # 7) „externe Funktionen“-Package
    # ─────────────────────────────────────────────────────────────────
    if external_fns:
        lines.append("")
        lines.append('package "externe Funktionen" as externe {')
        modules: Dict[str, List[str]] = defaultdict(list)
        for fn in external_fns:
            modules[name2module[fn]].append(fn)

        for mod, fns in sorted(modules.items()):
            pkg_alias = esc(f"externale__{mod}")
            lines.append(f'  package "{mod}.py" as {pkg_alias} {{')
            for fn in sorted(fns):
                lines.append(f'    component "{fn}" as {func2alias[fn]}')
            lines.append("  }")
        lines.append("}")
        lines.append("")

    # ─────────────────────────────────────────────────────────────────
    # 8) Funktions-Kanten erzeugen
    # ─────────────────────────────────────────────────────────────────
    added: set[tuple[str, str]] = set()
    for rel, meta in code_tree.items():
        for fn, fn_meta in meta.get("functions", {}).items():
            src = func2alias[fn]
            for called in fn_meta.get("calls", []):
                dst = func2alias.get(called)
                if not dst or dst == src:
                    continue
                # keine Kanten innerhalb derselben Datei
                if file_of_alias.get(dst) == file_of_alias.get(src):
                    continue
                if (src, dst) in added:
                    continue
                added.add((src, dst))
                lines.append(f"{src} ..> {dst} : {called}()")

    lines.append("@enduml")
    return "\n".join(lines)




# ════════════════════════════════════════════════════════════════════════
# 1) Start- und Projekt­auswahl
# ════════════════════════════════════════════════════════════════════════
@bp.route("/")
def index():
    settings = utils.read_settings()
    return redirect(
        url_for("main.project" if settings.get("token")
                else "main.settings_page")
    )

@bp.route("/project", methods=["GET", "POST"])
def project():
    settings = utils.read_settings()
    if not settings.get("token"):
        return redirect(url_for("main.settings_page"))

    form = ProjectForm()
    form.project.choices = [
        (k, k) for k in sorted(settings.get("projects", {}))
    ]
    if form.validate_on_submit():
        session["project"] = form.project.data
        return redirect(url_for("main.select_files"))
    return render_template("project.html", form=form)

# ════════════════════════════════════════════════════════════════════════
# 2) Dateiliste anzeigen
# ════════════════════════════════════════════════════════════════════════
@bp.route("/select_files")
def select_files():
    settings    = utils.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    repo_url  = settings["projects"].get(project_key)
    file_list = utils.get_flat_file_list(repo_url, token)

    flat_list = [
        {"filename": p, "indent": p.count("/") - 1}
        for p in file_list
    ]
    return render_template("select_files.html",
                           flat_list=flat_list, project=project_key)

# ════════════════════════════════════════════════════════════════════════
# 3) Gesamtausgabe / Analyse / UML
# ════════════════════════════════════════════════════════════════════════

@bp.route("/full_output", methods=["POST"])
def full_output():
    # ------------------------------------------------------------------
    # 0) Basisdaten
    # ------------------------------------------------------------------
    settings    = utils.read_settings()
    token       = settings.get("token", "")
    project_key = session.get("project")
    if not token or not project_key:
        return redirect(url_for("main.project"))

    selected_paths = request.form.getlist("selected_paths")
    repo_url       = settings["projects"].get(project_key)

    # ------------------------------------------------------------------
    # 1) ZIP laden  +  Analyse  (abfangen aller Fehler)
    # ------------------------------------------------------------------
    try:
        structure_str, content_str, analysis_rows, code_tree, \
            alias_warnings, import_conflicts = utils.get_zip_full_output(
                repo_url, token, selected_paths, analyse=True
        )
    except Exception as exc:
        print("[gitload] Analyse-Fehler:", exc)      # Konsole
        return render_template("full_output.html",   # 👉 gültige Response
                               error=f"Analyse-Fehler: {exc}")

    # Wenn get_zip_full_output() explizit None liefert
    if structure_str is None:
        return render_template("full_output.html",
                               error="Fehler beim Laden.")

    # ------------------------------------------------------------------
    # 2) Daten für die Tabs aufbereiten  (UNVERÄNDERT)
    # ------------------------------------------------------------------
    # ── Imports sammeln ───────────────────────────────────────────
    imports_rows = [
        {"file": rel, **imp}
        for rel, info in code_tree.items()
        for imp in info.get("imports", [])
    ]
    imports_rows.sort(key=lambda r: (r["file"], r["lineno"]))
    imports_copy = ""
    if imports_rows:
        headers = ["file","lineno","type","module","name","alias"]
        lines = ["\t".join(headers)]
        for r in imports_rows:
            lines.append("\t".join(str(r.get(c, "")) for c in headers))
        imports_copy = "\n".join(lines)

    # ── Funktions-Markdown (Tabellen-Ansicht) ─────────────────────
    if analysis_rows:
        known     = ["file", "func", "route", "class", "lineno"]
        col_order = [c for c in known if c in analysis_rows[0]] \
                    or list(analysis_rows[0].keys())
        md_head = "| " + " | ".join(col_order) + " |"
        md_sep  = "| " + " | ".join(["---"] * len(col_order)) + " |"
        md_body = [
            "| " + " | ".join(str(r.get(c, "")) for c in col_order) + " |"
            for r in analysis_rows
        ]
        analysis_markdown = "\n".join([md_head, md_sep, *md_body])
    else:
        col_order, analysis_markdown = [], ""

    # ── Codebaum-String erzeugen ─────────────────────────────────
    def build_tree(flat: dict) -> dict:
        root = {}
        for rel, info in flat.items():
            parts = rel.strip().split("/")
            ptr = root
            for p in parts[:-1]:
                ptr = ptr.setdefault(p, {})
            ptr[parts[-1]] = info
        return root

    def fmt_dir(node: dict, pref: str = "") -> list[str]:
        """
        Erzeugt einen ASCII-Baum der Dateien/Funktionen.
        Mehrstufig verschachtelte Funktionen werden beliebig tief
        eingerückt ausgegeben.
        """
        out: list[str] = []
        keys = sorted(node)

        for i, name in enumerate(keys):
            last       = i == len(keys) - 1
            branch     = "└── " if last else "├── "
            next_pref  = pref + ("    " if last else "│   ")
            sub        = node[name]

            # ───────── Ordner / Unterpakete ───────────────────────────
            if isinstance(sub, dict) and "functions" not in sub:
                out.append(f"{pref}{branch}{name}/")
                out.extend(fmt_dir(sub, next_pref))
                continue

            # ───────── Datei ──────────────────────────────────────────
            out.append(f"{pref}{branch}{name}")

            # Hilfsfunktion für rekursive Ausgabe einer Funktion
            def print_fn(fn_name: str,
                         nested_map: dict[str, list[str]],
                         prefix: str,
                         is_last: bool) -> None:
                route = sub["functions"][fn_name].get("route", "")
                fn_branch = "└── " if is_last else "├── "
                out.append(f"{prefix}{fn_branch}{fn_name}()"
                           f"{('  route: '+route) if route else ''}")

                kids = sorted(nested_map.get(fn_name, []))
                if not kids:
                    return

                kid_pref_base = prefix + ("    " if is_last else "│   ")
                for k, kid in enumerate(kids):
                    kid_last = k == len(kids) - 1
                    print_fn(kid, nested_map, kid_pref_base, kid_last)

            nested_map = sub.get("nested", {})
            funcs = sorted(sub.get("functions", {}))
            for j, fn in enumerate(funcs):
                fn_last = j == len(funcs) - 1
                print_fn(fn, nested_map, next_pref, fn_last)

        return out


    code_tree_str = "\n".join(fmt_dir(build_tree(code_tree)))

    # ── UML-Script ────────────────────────────────────────────────
    uml_code = build_package_uml(code_tree)

    # ── Kombinierten Text (Struktur + Inhalte) ─────────────────────
    combined_text = (
        "Struktur der ZIP-Datei:\n" + structure_str + "\n\n" +
        "Einsicht in die Dateien:\n" + content_str
    )

    # ------------------------------------------------------------------
    # 3) Endgültiges Rendering
    # ------------------------------------------------------------------
    return render_template(
        "full_output.html",
        combined_text     = combined_text,
        analysis_rows     = analysis_rows,
        analysis_markdown = analysis_markdown,
        col_order         = col_order,
        imports_rows      = imports_rows,
        imports_copy      = imports_copy,
        code_tree_str     = code_tree_str,
        uml_code          = uml_code,
        alias_warnings    = alias_warnings,
        import_conflicts  = import_conflicts,
    )



# ════════════════════════════════════════════════════════════════════════
# 4) Einstellungen
# ════════════════════════════════════════════════════════════════════════
@bp.route("/settings", methods=["GET", "POST"])
def settings_page():
    settings = utils.read_settings()
    if request.method == "POST":
        new_token = request.form.get("token", "").strip()
        names     = request.form.getlist("project_name[]")
        urls      = request.form.getlist("project_url[]")

        projects = {n.strip(): u.strip()
                    for n, u in zip(names, urls) if n.strip() and u.strip()}

        utils.write_settings({"token": new_token, "projects": projects})
        session["token"] = new_token
        return redirect(url_for("main.project"))

    return render_template(
        "settings.html",
        token=settings.get("token", ""),
        projects=settings.get("projects", {})
    )
