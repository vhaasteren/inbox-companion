#!/usr/bin/env python3
from __future__ import annotations
import sys, ast, os
from pathlib import Path
from typing import Optional

PY_EXTS = {".py"}

def ann_to_str(node: Optional[ast.AST]) -> str:
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return "Any"

def default_to_str(node: Optional[ast.AST]) -> str:
    if node is None:
        return ""
    try:
        s = ast.unparse(node)
        return f"={s}"
    except Exception:
        return ""

def fmt_params(args: ast.arguments) -> str:
    parts: list[str] = []

    posonly = getattr(args, "posonlyargs", [])
    po_count = len(posonly)
    total_non_kwonly = po_count + len(args.args)
    first_default_index = total_non_kwonly - len(args.defaults)

    for i, a in enumerate(posonly):
        default = ""
        if args.defaults and i >= first_default_index:
            default = default_to_str(args.defaults[i - first_default_index])
        parts.append(f"{a.arg}: {ann_to_str(a.annotation)}{default}")
    if posonly:
        parts.append("/")

    for i, a in enumerate(args.args):
        default = ""
        idx_from_start = i + po_count
        if args.defaults and idx_from_start >= first_default_index:
            default = default_to_str(args.defaults[idx_from_start - first_default_index])
        parts.append(f"{a.arg}: {ann_to_str(a.annotation)}{default}")

    if args.vararg:
        parts.append(f"*{args.vararg.arg}: {ann_to_str(args.vararg.annotation)}")
    elif args.kwonlyargs:
        parts.append("*")

    for i, a in enumerate(args.kwonlyargs):
        default = default_to_str(args.kw_defaults[i]) if args.kw_defaults else ""
        parts.append(f"{a.arg}: {ann_to_str(a.annotation)}{default}")

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}: {ann_to_str(args.kwarg.annotation)}")

    return ", ".join(parts)

def signature_of_function(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    params = fmt_params(fn.args)
    ret = ann_to_str(fn.returns)
    async_prefix = "async " if isinstance(fn, ast.AsyncFunctionDef) else ""
    return f"{async_prefix}def {fn.name}({params}) -> {ret}"

def walk_python_file(path: Path) -> list[str]:
    out: list[str] = []
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return out
    try:
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return out

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(signature_of_function(node))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = []
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(signature_of_function(n))
            if methods:
                out.append(f"class {node.name}:")
                out.extend(f"  {m}" for m in methods)
    return out

def main():
    if len(sys.argv) < 2:
        print("Usage: py_api.py <root_dir> [<root_dir>...]", file=sys.stderr)
        sys.exit(2)

    roots = [Path(p).resolve() for p in sys.argv[1:] if Path(p).exists()]
    repo_root = Path.cwd()

    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.suffix in PY_EXTS and p.is_file():
                lines = walk_python_file(p)
                if not lines:
                    continue
                rel = os.path.relpath(str(p), start=str(repo_root))
                print(f"===== {rel} =====")
                for line in lines:
                    print(line)
                print()

if __name__ == "__main__":
    main()

