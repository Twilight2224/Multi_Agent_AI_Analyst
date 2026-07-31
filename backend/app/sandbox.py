"""Constrained Python runner for the code agent.

The generated program is AST-checked, gets no imports/files/network, runs in an
empty temporary directory, and is killed after a short timeout. For higher-risk
production use, put this service in a separate container or microVM.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile


ALLOWED_CALLS = {"print", "sum", "len", "min", "max", "round", "abs", "sorted", "range"}
FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.With, ast.Try, ast.ClassDef, ast.AsyncFunctionDef, ast.Lambda)


class SafeCodeVisitor(ast.NodeVisitor):
    def visit(self, node: ast.AST) -> None:
        if isinstance(node, FORBIDDEN_NODES):
            raise ValueError(f"{type(node).__name__} is not allowed in sandbox code")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("dunder attribute access is not allowed")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("dunder names are not allowed")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in ALLOWED_CALLS:
            raise ValueError(f"call to {node.func.id!r} is not allowed")
        super().visit(node)


def run_safe_python(code: str, timeout_seconds: int = 3) -> str:
    if len(code) > 4000:
        raise ValueError("Generated code is too long")
    tree = ast.parse(code, mode="exec")
    SafeCodeVisitor().visit(tree)
    with tempfile.TemporaryDirectory(prefix="agent-sandbox-") as directory:
        environment = {"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")}
        completed = subprocess.run(
            [sys.executable, "-I", "-c", code], cwd=directory, env=environment,
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
    if completed.returncode != 0:
        raise ValueError(f"Sandbox execution failed: {completed.stderr[-500:]}")
    return completed.stdout.strip() or "(program produced no output)"
