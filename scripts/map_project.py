#!/usr/bin/env python3
"""
Phase 1: Build a dependency graph + call graph + class model for a codebase.

Walks the project, parses supported languages, extracts:
  - file -> file edges (via imports)
  - function/class definitions with one-line headers
  - **call edges** (function -> function), Python AST-precise, JS/TS regex
  - **class hierarchy** (class -> base classes, fields, methods)
  - API endpoint declarations (FastAPI, Flask, Express, Next.js, etc.)
  - external integration markers (Supabase, Telegram, OpenAI, scientific Python, ...)

Outputs project-map.json, project-map.mmd, and class_diagram.mmd.

Designed to be dependency-light. Optional deps: pathspec.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import pathspec  # type: ignore
    HAS_PATHSPEC = True
except ImportError:
    HAS_PATHSPEC = False

# progress heartbeat (no-op if file unwritable)
sys.path.insert(0, str(Path(__file__).parent))
try:
    import _progress
except Exception:
    class _progress:  # type: ignore
        @staticmethod
        def start(*a, **k): pass
        @staticmethod
        def update(*a, **k): pass
        @staticmethod
        def done(*a, **k): pass


# ---------- file walking ----------

DEFAULT_IGNORES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".cartographer",
    "dist", "build", ".next", ".turbo", "coverage", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "target", ".idea", ".vscode",
}

SUPPORTED_EXT = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go",
}


def load_gitignore(root: Path):
    if not HAS_PATHSPEC:
        return None
    gi = root / ".gitignore"
    if not gi.exists():
        return None
    with open(gi) as f:
        return pathspec.PathSpec.from_lines("gitwildmatch", f)


def iter_source_files(root: Path):
    spec = load_gitignore(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORES]
        for fn in filenames:
            ext = Path(fn).suffix.lower()
            if ext not in SUPPORTED_EXT:
                continue
            full = Path(dirpath) / fn
            rel = full.relative_to(root)
            if spec and spec.match_file(str(rel)):
                continue
            yield full, rel


# ---------- integration detectors ----------

INTEGRATIONS = {
    "supabase":     [r"\bsupabase\b", r"@supabase/", r"createClient\("],
    "telegram":     [r"python-telegram-bot", r"telegraf", r"node-telegram-bot-api",
                     r"\btelegram\b", r"\bbot\.send_message\b", r"\bTelegramBot\b"],
    "vercel":       [r"@vercel/", r"vercel\.json", r"\bvercel\b"],
    "railway":      [r"railway\.json", r"\brailway\b"],
    "openai":       [r"\bopenai\b", r"OpenAI\(", r"openai\.ChatCompletion"],
    "anthropic":    [r"\banthropic\b", r"Anthropic\(", r"claude-3", r"claude-sonnet",
                     r"claude-opus"],
    "google_api":   [r"google-cloud", r"googleapis", r"google\.cloud"],
    "aws":          [r"\bboto3\b", r"@aws-sdk/", r"\baws-sdk\b"],
    "stripe":       [r"\bstripe\b", r"Stripe\("],
    "redis":        [r"\bredis\b", r"ioredis"],
    "postgres":     [r"\bpsycopg\b", r"\basyncpg\b", r"pg-promise", r"\bpg\b"],
    "mongo":        [r"\bpymongo\b", r"mongoose", r"\bMongoClient\b"],
    "queue":        [r"\bcelery\b", r"\brq\b", r"\bbullmq\b", r"\brabbitmq\b",
                     r"\bkafka\b"],
    "websocket":    [r"\bwebsocket\b", r"\bwebsockets\b", r"socket\.io"],
    "sqlalchemy":   [r"\bsqlalchemy\b"],
    "prisma":       [r"@prisma/client", r"\bprisma\b"],
    # scientific / data-science Python
    "pandas":       [r"\bimport pandas\b", r"\bfrom pandas\b", r"\bpd\."],
    "numpy":        [r"\bimport numpy\b", r"\bfrom numpy\b", r"\bnp\.\w"],
    "scipy":        [r"\bimport scipy\b", r"\bfrom scipy\b"],
    "sklearn":      [r"\bsklearn\b", r"scikit-learn"],
    "yfinance":     [r"\byfinance\b"],
    "pyarrow":      [r"\bpyarrow\b", r"\.parquet\b"],
    "matplotlib":   [r"\bmatplotlib\b", r"\bplt\."],
    "seaborn":      [r"\bseaborn\b", r"\bsns\."],
    "torch":        [r"\bimport torch\b", r"\bfrom torch\b"],
    "tensorflow":   [r"\bimport tensorflow\b", r"\bfrom tensorflow\b"],
    "huggingface":  [r"\bhuggingface\b", r"\btransformers\b", r"\bdatasets\b"],
    # fastapi / flask explicit (lets the matcher boost backend-api specialists)
    "fastapi":      [r"\bfrom fastapi\b", r"\bimport fastapi\b", r"\bFastAPI\("],
    "flask":        [r"\bfrom flask\b", r"\bimport flask\b", r"\bFlask\("],
    "express":      [r"\bexpress\b", r"\brequire\(['\"]express['\"]\)"],
    "react":        [r"\bfrom ['\"]react['\"]", r"\breact-dom\b"],
    "nextjs":       [r"\bnext/router\b", r"\bnext/navigation\b", r"\bnext/server\b",
                     r"\bnext\.config\b"],
    # mobile
    "react_native": [r"\bfrom ['\"]react-native['\"]", r"\b@react-native\b"],
    "expo":         [r"\bfrom ['\"]expo[-/]", r"\bexpo-modules\b", r"\bexpo-router\b"],
    "flutter":      [r"\bimport 'package:flutter/", r"\bflutter:\s*sdk:"],
    "ionic":        [r"\b@ionic/", r"\bionic-native\b"],
    "capacitor":    [r"\b@capacitor/"],
    # cli frameworks
    "click":        [r"\bimport click\b", r"\bfrom click\b", r"@click\.command"],
    "typer":        [r"\bimport typer\b", r"\bfrom typer\b", r"\btyper\.Typer\("],
    "argparse":     [r"\bimport argparse\b", r"\bargparse\.ArgumentParser\b"],
    "cobra":        [r"github\.com/spf13/cobra"],
    "commander":    [r"\bfrom ['\"]commander['\"]", r"\brequire\(['\"]commander['\"]\)"],
    "yargs":        [r"\bfrom ['\"]yargs['\"]", r"\brequire\(['\"]yargs['\"]\)"],
    "clap":         [r"\buse clap::"],
    "oclif":        [r"\b@oclif/"],
    # test frameworks
    "pytest":       [r"\bimport pytest\b", r"\bfrom pytest\b", r"@pytest\."],
    "unittest":     [r"\bimport unittest\b", r"\bunittest\.TestCase\b"],
    "jest":         [r"\b@jest/", r"\bdescribe\(\s*['\"]", r"\btest\(\s*['\"]"],
    "vitest":       [r"\bfrom ['\"]vitest['\"]"],
    "mocha":        [r"\bfrom ['\"]mocha['\"]", r"\brequire\(['\"]mocha['\"]\)"],
    "playwright":   [r"\b@playwright/", r"\bplaywright/test\b"],
    "cypress":      [r"\bcypress\b", r"\bcy\.\w"],
    "testing_library": [r"\b@testing-library/"],
    "hypothesis":   [r"\bfrom hypothesis\b", r"@given\("],
    # filesystem stays but is demoted (segmenter ignores it as primary marker)
    "filesystem":   [r"\bos\.path\b", r"\bpathlib\b", r"fs\.readFile", r"fs/promises"],
}

INTEGRATION_PATTERNS = {
    label: [re.compile(p, re.IGNORECASE) for p in patterns]
    for label, patterns in INTEGRATIONS.items()
}

# Integrations the segmenter should NOT use as a primary segment-naming key
# (too broad — they appear in nearly every file)
LOW_SIGNAL_INTEGRATIONS = {"filesystem"}


# ---------- endpoint detectors ----------

ENDPOINT_PATTERNS = [
    (re.compile(r"@(?:\w+)\.(get|post|put|patch|delete|head|options)\(\s*['\"]([^'\"]+)['\"]"), "rest"),
    (re.compile(r"@\w+\.route\(\s*['\"]([^'\"]+)['\"](?:.*?methods\s*=\s*\[([^\]]+)\])?", re.S), "flask_route"),
    (re.compile(r"(?<!@)\b(?:app|router)\.(get|post|put|patch|delete|use)\(\s*['\"]([^'\"]+)['\"]"), "express"),
    (re.compile(r"export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE)\b"), "nextjs"),
]


# ---------- data classes ----------

@dataclass
class Symbol:
    id: str             # "file::QualName" e.g. "src/foo.py::MyClass.bar"
    name: str
    qualname: str       # "MyClass.bar" for methods, "bar" for functions
    kind: str           # "function" | "class" | "method"
    file: str
    line: int
    header: str = ""
    class_of: str = ""  # if method: parent class name


@dataclass
class ClassInfo:
    id: str
    name: str
    file: str
    line: int
    bases: list[str] = field(default_factory=list)     # base class names
    methods: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)


@dataclass
class CallEdge:
    caller_id: str      # symbol id of caller (e.g. "src/foo.py::bar")
    callee_name: str    # raw callee name as appeared in source
    callee_id: str = "" # filled by resolver — symbol id, or "" if external/unresolved
    file: str = ""
    line: int = 0


@dataclass
class Endpoint:
    method: str
    path: str
    file: str
    line: int
    framework: str
    handler_id: str = ""  # symbol id of the handler function (filled if resolvable)


@dataclass
class FileNode:
    path: str
    lang: str
    loc: int
    imports: list[str] = field(default_factory=list)
    integrations: list[str] = field(default_factory=list)
    symbol_count: int = 0


@dataclass
class ProjectMap:
    root: str
    files: list[FileNode] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    calls: list[CallEdge] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    integration_index: dict[str, list[str]] = field(default_factory=dict)
    parse_errors: list[str] = field(default_factory=list)
    ts_path_aliases: dict[str, str] = field(default_factory=dict)


# ---------- python parsing (precise, AST) ----------

def parse_python(rel_path: str, src: str, pmap: ProjectMap) -> FileNode:
    node = FileNode(path=rel_path, lang="python", loc=src.count("\n") + 1)
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        pmap.parse_errors.append(f"{rel_path}: {e}")
        return node

    # imports
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for alias in n.names:
                node.imports.append(alias.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                node.imports.append(n.module)

    # classes + their methods, top-level functions, calls
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            _emit_class(n, rel_path, src, pmap, node)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _emit_function(n, rel_path, src, pmap, node, qualname=n.name, class_of="")
            _emit_calls_in(n, f"{rel_path}::{n.name}", rel_path, pmap)

    return node


def _emit_class(node: ast.ClassDef, rel_path: str, src: str,
                pmap: ProjectMap, fnode: FileNode):
    bases = [_unparse(b) for b in node.bases]
    cls_id = f"{rel_path}::{node.name}"
    info = ClassInfo(id=cls_id, name=node.name, file=rel_path, line=node.lineno, bases=bases)

    pmap.symbols.append(Symbol(
        id=cls_id, name=node.name, qualname=node.name, kind="class",
        file=rel_path, line=node.lineno, header=_docstring_first_line(node) or "",
    ))
    fnode.symbol_count += 1

    for n in node.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = f"{node.name}.{n.name}"
            sym_id = f"{rel_path}::{qual}"
            info.methods.append(n.name)
            pmap.symbols.append(Symbol(
                id=sym_id, name=n.name, qualname=qual, kind="method",
                file=rel_path, line=n.lineno,
                header=_docstring_first_line(n) or "",
                class_of=node.name,
            ))
            fnode.symbol_count += 1
            _emit_calls_in(n, sym_id, rel_path, pmap)
            # collect fields from self.X = ... in __init__
            if n.name == "__init__":
                for stmt in ast.walk(n):
                    if isinstance(stmt, ast.Assign):
                        for tgt in stmt.targets:
                            if (isinstance(tgt, ast.Attribute)
                                    and isinstance(tgt.value, ast.Name)
                                    and tgt.value.id == "self"):
                                if tgt.attr not in info.fields:
                                    info.fields.append(tgt.attr)
        elif isinstance(n, ast.Assign):
            # class-level fields: x = ...
            for tgt in n.targets:
                if isinstance(tgt, ast.Name) and tgt.id not in info.fields:
                    info.fields.append(tgt.id)
        elif isinstance(n, ast.AnnAssign):
            # class-level annotated fields: x: int = ...
            if isinstance(n.target, ast.Name) and n.target.id not in info.fields:
                info.fields.append(n.target.id)

    pmap.classes.append(info)


def _emit_function(node, rel_path: str, src: str, pmap: ProjectMap,
                   fnode: FileNode, qualname: str, class_of: str):
    sym_id = f"{rel_path}::{qualname}"
    pmap.symbols.append(Symbol(
        id=sym_id, name=node.name, qualname=qualname, kind="function",
        file=rel_path, line=node.lineno,
        header=_docstring_first_line(node) or "",
        class_of=class_of,
    ))
    fnode.symbol_count += 1


def _emit_calls_in(scope_node, caller_id: str, rel_path: str, pmap: ProjectMap):
    """Walk a function/method body and record every Call node."""
    for n in ast.walk(scope_node):
        if isinstance(n, ast.Call):
            name = _call_name(n.func)
            if not name:
                continue
            pmap.calls.append(CallEdge(
                caller_id=caller_id, callee_name=name,
                file=rel_path, line=getattr(n, "lineno", 0),
            ))


def _call_name(func: ast.AST) -> str:
    """Best-effort stringification of the callee.
    Examples: foo() -> "foo", obj.method() -> "obj.method", a.b.c() -> "a.b.c"
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = _call_name(func.value)
        return f"{base}.{func.attr}" if base else func.attr
    return ""


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_unparse(node.value)}.{node.attr}"
        return ""


def _docstring_first_line(node) -> str | None:
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.value.value.strip().split("\n", 1)[0][:120]
    return None


# ---------- js/ts parsing (regex, best-effort) ----------

JS_IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*
        (?:import\s+(?:.+?\s+from\s+)?['"]([^'"]+)['"]
         |  (?:const|let|var)\s+\w+\s*=\s*require\(\s*['"]([^'"]+)['"]\s*\))
    """,
    re.X,
)
JS_FN_RE = re.compile(
    r"""(?:^|\n)\s*
        (?:export\s+)?
        (?:async\s+)?
        (?:function\s+(\w+)
         |  (?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()
    """,
    re.X,
)
JS_CLASS_RE = re.compile(
    r"(?:^|\n)\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+([\w.]+))?"
)
JS_CALL_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")


def parse_js_like(rel_path: str, src: str, pmap: ProjectMap, lang: str) -> FileNode:
    node = FileNode(path=rel_path, lang=lang, loc=src.count("\n") + 1)

    for m in JS_IMPORT_RE.finditer(src):
        node.imports.append(m.group(1) or m.group(2))

    # functions
    for m in JS_FN_RE.finditer(src):
        name = m.group(1) or m.group(2)
        if not name:
            continue
        line = src[: m.start()].count("\n") + 1
        sym_id = f"{rel_path}::{name}"
        pmap.symbols.append(Symbol(
            id=sym_id, name=name, qualname=name,
            kind="function", file=rel_path, line=line,
        ))
        node.symbol_count += 1

    # classes
    for m in JS_CLASS_RE.finditer(src):
        cname = m.group(1)
        base = m.group(2)
        line = src[: m.start()].count("\n") + 1
        cls_id = f"{rel_path}::{cname}"
        pmap.symbols.append(Symbol(
            id=cls_id, name=cname, qualname=cname,
            kind="class", file=rel_path, line=line,
        ))
        pmap.classes.append(ClassInfo(
            id=cls_id, name=cname, file=rel_path, line=line,
            bases=[base] if base else [],
        ))
        node.symbol_count += 1

    # crude call extraction at file scope (not per-function — we don't have scopes)
    # caller_id is the file itself; the synthesizer will treat this as approximate
    KW = {"if", "for", "while", "switch", "return", "function", "catch",
          "typeof", "new", "throw", "await", "yield", "async", "class"}
    for m in JS_CALL_RE.finditer(src):
        callee = m.group(1)
        if callee in KW:
            continue
        line = src[: m.start()].count("\n") + 1
        pmap.calls.append(CallEdge(
            caller_id=f"{rel_path}::__file__", callee_name=callee,
            file=rel_path, line=line,
        ))

    return node


# ---------- go parsing (regex) ----------

GO_IMPORT_RE = re.compile(r'import\s*\(\s*((?:.|\n)*?)\)')
GO_IMPORT_LINE_RE = re.compile(r'"([^"]+)"')
GO_FN_RE = re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.M)


def parse_go(rel_path: str, src: str, pmap: ProjectMap) -> FileNode:
    node = FileNode(path=rel_path, lang="go", loc=src.count("\n") + 1)
    for block in GO_IMPORT_RE.finditer(src):
        for imp in GO_IMPORT_LINE_RE.findall(block.group(1)):
            node.imports.append(imp)
    for m in GO_FN_RE.finditer(src):
        line = src[: m.start()].count("\n") + 1
        name = m.group(1)
        pmap.symbols.append(Symbol(
            id=f"{rel_path}::{name}", name=name, qualname=name,
            kind="function", file=rel_path, line=line,
        ))
        node.symbol_count += 1
    return node


# ---------- endpoint & integration scan ----------

def scan_endpoints_and_integrations(rel_path: str, src: str, pmap: ProjectMap, node: FileNode):
    for pattern, fw in ENDPOINT_PATTERNS:
        for m in pattern.finditer(src):
            line = src[: m.start()].count("\n") + 1
            if fw == "flask_route":
                path = m.group(1)
                methods = m.group(2) or "GET"
                methods = re.findall(r"['\"](\w+)['\"]", methods) or ["GET"]
                for method in methods:
                    pmap.endpoints.append(Endpoint(method.upper(), path, rel_path, line, fw))
            elif fw == "nextjs":
                path = "/" + str(Path(rel_path).parent).replace(os.sep, "/")
                pmap.endpoints.append(Endpoint(m.group(1).upper(), path, rel_path, line, fw))
            else:
                method, path = m.group(1), m.group(2)
                pmap.endpoints.append(Endpoint(method.upper(), path, rel_path, line, fw))

    found = set()
    for label, patterns in INTEGRATION_PATTERNS.items():
        for pat in patterns:
            if pat.search(src):
                found.add(label)
                break
    node.integrations = sorted(found)
    for label in found:
        pmap.integration_index.setdefault(label, []).append(rel_path)


# ---------- TS path-alias resolution ----------

def load_ts_path_aliases(root: Path) -> dict[str, str]:
    """Read tsconfig.json compilerOptions.paths into a flat alias->target map.

    Conservative: handles the common case `"@/*": ["src/*"]`. Returns
    paths relative to the project root.
    """
    aliases = {}
    for tsconfig_name in ("tsconfig.json", "frontend/tsconfig.json", "frontend/tsconfig.app.json"):
        p = root / tsconfig_name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            # strip // comments and trailing commas (tsconfig is JSON-with-comments)
            text = re.sub(r"//[^\n]*", "", text)
            text = re.sub(r",(\s*[}\]])", r"\1", text)
            cfg = json.loads(text)
        except Exception:
            continue
        co = cfg.get("compilerOptions", {})
        base_url = co.get("baseUrl", ".")
        ts_dir = p.parent.relative_to(root) if p.parent != root else Path(".")
        base = (ts_dir / base_url).as_posix().lstrip("./") or "."
        for alias, targets in (co.get("paths") or {}).items():
            if not targets:
                continue
            target = targets[0]
            alias_clean = alias.rstrip("/*")
            target_clean = (Path(base) / target.rstrip("/*")).as_posix().lstrip("./")
            aliases[alias_clean] = target_clean
    return aliases


# ---------- import resolution (file -> file edges) ----------

def resolve_imports_to_edges(pmap: ProjectMap, root: Path):
    by_module = {}
    for f in pmap.files:
        p = Path(f.path)
        stem = p.with_suffix("").as_posix()
        by_module[stem] = f.path
        by_module[p.stem] = f.path
        # also index parent dir as resolving to __init__/index files
        if p.stem in {"__init__", "index"}:
            by_module[p.parent.as_posix()] = f.path

    aliases = pmap.ts_path_aliases

    for f in pmap.files:
        for imp in f.imports:
            # resolve TS aliases first: "@/components/Foo" -> "src/components/Foo"
            resolved = imp
            for alias, target in aliases.items():
                if imp == alias or imp.startswith(alias + "/"):
                    resolved = target + imp[len(alias):]
                    break

            candidates = [
                resolved,
                resolved.replace(".", "/"),
                resolved.lstrip("./"),
                resolved.split("/")[-1] if "/" in resolved else resolved,
            ]
            # also try Path-relative resolution if import starts with "./" or "../"
            if imp.startswith((".", "/")):
                here = Path(f.path).parent
                rel_target = (here / imp).resolve()
                try:
                    rel_str = rel_target.relative_to(root.resolve()).as_posix()
                    candidates.insert(0, rel_str)
                except Exception:
                    pass

            for c in candidates:
                c = c.rstrip("/")
                if c in by_module and by_module[c] != f.path:
                    pmap.edges.append((f.path, by_module[c]))
                    break


# ---------- call resolution (callee_name -> callee symbol id) ----------

def resolve_calls(pmap: ProjectMap):
    """Resolve callee_name to a project-internal symbol id where possible.

    Strategy (in order):
      1. If `caller_file::callee_name` matches a known symbol id, use it.
      2. If callee is "obj.method" and a class with that method exists in the
         caller's reachable file set, prefer that.
      3. Otherwise, if any project symbol has that bare name, link to the
         lexicographically first match (best-effort).
      4. Else leave callee_id="" (external / unresolved).
    """
    by_id = {s.id: s for s in pmap.symbols}
    by_name = {}
    by_qualname = {}
    for s in pmap.symbols:
        by_name.setdefault(s.name, []).append(s.id)
        by_qualname.setdefault(s.qualname, []).append(s.id)

    # files reachable from each file via 1-hop edges
    reachable = {}
    for src, dst in pmap.edges:
        reachable.setdefault(src, set()).add(dst)

    for c in pmap.calls:
        callee = c.callee_name
        caller_file = c.file

        # 1. same-file definition
        sid = f"{caller_file}::{callee}"
        if sid in by_id:
            c.callee_id = sid
            continue

        # 2. obj.method form — try matching by qualname first, then by method name
        if "." in callee:
            tail = callee.split(".")[-1]
            qual = callee
            # match Class.method exactly
            if qual in by_qualname:
                cands = by_qualname[qual]
                # prefer one in caller_file or its reachable set
                pick = _pick_in_reachable(cands, caller_file, reachable, by_id)
                if pick:
                    c.callee_id = pick
                    continue
            # else just try the method name
            if tail in by_name:
                pick = _pick_in_reachable(by_name[tail], caller_file, reachable, by_id)
                if pick:
                    c.callee_id = pick
                    continue

        # 3. bare name lookup
        if callee in by_name:
            pick = _pick_in_reachable(by_name[callee], caller_file, reachable, by_id)
            if pick:
                c.callee_id = pick
                continue

        # 4. unresolved (probably external/stdlib/builtin)
        c.callee_id = ""


def _pick_in_reachable(candidates, caller_file, reachable, by_id):
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    in_file = [c for c in candidates if by_id[c].file == caller_file]
    if in_file:
        return in_file[0]
    in_reach = [c for c in candidates if by_id[c].file in reachable.get(caller_file, set())]
    if in_reach:
        return in_reach[0]
    return sorted(candidates)[0]


# ---------- mermaid render ----------

def render_file_graph(pmap: ProjectMap) -> str:
    lines = ["graph LR"]
    seen = set()
    def node_id(path: str) -> str:
        return "n_" + re.sub(r"\W+", "_", path)[:60]
    for src, dst in pmap.edges:
        a, b = node_id(src), node_id(dst)
        if a not in seen:
            lines.append(f'  {a}["{src}"]')
            seen.add(a)
        if b not in seen:
            lines.append(f'  {b}["{dst}"]')
            seen.add(b)
        lines.append(f"  {a} --> {b}")
    return "\n".join(lines)


def render_class_diagram(pmap: ProjectMap, max_classes: int = 80) -> str:
    """Mermaid classDiagram of project classes (limited for readability)."""
    classes = pmap.classes[:max_classes]
    if not classes:
        return "classDiagram\n  %% no classes detected"
    lines = ["classDiagram"]
    cls_names = {c.name for c in classes}
    for c in classes:
        lines.append(f"  class {_safe_id(c.name)}")
        for m in c.methods[:8]:
            lines.append(f"    {_safe_id(c.name)} : {m}()")
        for fld in c.fields[:6]:
            lines.append(f"    {_safe_id(c.name)} : {fld}")
        for base in c.bases:
            base_simple = base.split(".")[-1]
            if base_simple in cls_names:
                lines.append(f"  {_safe_id(base_simple)} <|-- {_safe_id(c.name)}")
    return "\n".join(lines)


def _safe_id(s: str) -> str:
    return re.sub(r"\W+", "_", s) or "X"


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="Project root directory")
    ap.add_argument("--output", "-o", default=".cartographer", help="Output directory")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    pmap = ProjectMap(root=str(root))
    pmap.ts_path_aliases = load_ts_path_aliases(root)
    if pmap.ts_path_aliases:
        print(f"TS aliases: {pmap.ts_path_aliases}", file=sys.stderr)

    _progress.start("phase-1", out_dir=out)
    print(f"Walking {root}...", file=sys.stderr)
    n = 0
    for full, rel in iter_source_files(root):
        rel_str = rel.as_posix()
        try:
            src = full.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            pmap.parse_errors.append(f"{rel_str}: read error {e}")
            continue

        ext = full.suffix.lower()
        if ext == ".py":
            node = parse_python(rel_str, src, pmap)
        elif ext in {".js", ".jsx", ".mjs", ".cjs"}:
            node = parse_js_like(rel_str, src, pmap, "javascript")
        elif ext in {".ts", ".tsx"}:
            node = parse_js_like(rel_str, src, pmap, "typescript")
        elif ext == ".go":
            node = parse_go(rel_str, src, pmap)
        else:
            continue

        scan_endpoints_and_integrations(rel_str, src, pmap, node)
        pmap.files.append(node)
        n += 1
        if n % 50 == 0:
            print(f"  parsed {n} files", file=sys.stderr)
            _progress.update(step="parsing", current=n, total=0,
                             message=f"parsed {n} files")

    _progress.update(step="resolving imports", current=len(pmap.files),
                     total=len(pmap.files))
    print(f"Resolving imports...", file=sys.stderr)
    resolve_imports_to_edges(pmap, root)
    _progress.update(step="resolving calls",
                     current=0, total=len(pmap.calls),
                     message=f"{len(pmap.calls)} call sites")
    print(f"Resolving calls ({len(pmap.calls)} call sites)...", file=sys.stderr)
    resolve_calls(pmap)

    # link endpoints to handler symbols (best-effort)
    sym_by_file_line = {(s.file, s.line): s for s in pmap.symbols if s.kind in {"function", "method"}}
    for ep in pmap.endpoints:
        # find the next function definition at or after the endpoint's decorator line
        candidates = [s for (f, l), s in sym_by_file_line.items()
                      if f == ep.file and l >= ep.line]
        if candidates:
            best = min(candidates, key=lambda s: s.line - ep.line)
            ep.handler_id = best.id

    # write outputs
    map_path = out / "project-map.json"
    with open(map_path, "w") as f:
        json.dump({
            "root": pmap.root,
            "files": [asdict(x) for x in pmap.files],
            "edges": [list(e) for e in pmap.edges],
            "symbols": [asdict(s) for s in pmap.symbols],
            "classes": [asdict(c) for c in pmap.classes],
            "calls": [asdict(c) for c in pmap.calls],
            "endpoints": [asdict(e) for e in pmap.endpoints],
            "integration_index": pmap.integration_index,
            "ts_path_aliases": pmap.ts_path_aliases,
            "parse_errors": pmap.parse_errors,
            "stats": {
                "files": len(pmap.files),
                "edges": len(pmap.edges),
                "symbols": len(pmap.symbols),
                "classes": len(pmap.classes),
                "calls": len(pmap.calls),
                "calls_resolved": sum(1 for c in pmap.calls if c.callee_id),
                "endpoints": len(pmap.endpoints),
                "integrations": list(pmap.integration_index.keys()),
            },
        }, f, indent=2)

    mmd_path = out / "project-map.mmd"
    with open(mmd_path, "w") as f:
        f.write(render_file_graph(pmap))

    cls_path = out / "class_diagram.mmd"
    with open(cls_path, "w") as f:
        f.write(render_class_diagram(pmap))

    print(f"\nWrote {map_path}", file=sys.stderr)
    print(f"Wrote {mmd_path}", file=sys.stderr)
    print(f"Wrote {cls_path}", file=sys.stderr)
    resolved = sum(1 for c in pmap.calls if c.callee_id)
    print(f"Files: {len(pmap.files)}  Edges: {len(pmap.edges)}  "
          f"Symbols: {len(pmap.symbols)}  Classes: {len(pmap.classes)}  "
          f"Calls: {resolved}/{len(pmap.calls)} resolved  "
          f"Endpoints: {len(pmap.endpoints)}", file=sys.stderr)
    if pmap.integration_index:
        print(f"Integrations detected: {', '.join(sorted(pmap.integration_index.keys()))}", file=sys.stderr)
    _progress.done()


if __name__ == "__main__":
    main()
