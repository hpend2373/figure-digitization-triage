# -*- coding: utf-8 -*-
"""One machine's paths, found by parsing rather than grepping.

WHY THIS EXISTS. `paths.py` was written so that no path would be baked into a
file, and it then handed out `/tmp/intake6/draft`, `/home/claude/geo/verify`
and one person's home directory as its DEFAULTS. The crop harness required a
JSON map that nothing here writes. Both survived a rewrite that was about
exactly this, because nothing checked.

Parsed, not grepped: the prose in this repository discusses these paths
constantly - that is how the defects are recorded - and a line search cannot
tell a docstring explaining a defect from a literal reintroducing it. Only
string constants that are not docstrings count.

This file is skipped by its own scan: the prefixes it looks for have to be
written down somewhere, and one place that says so is better than an
exemption list nobody reads.
"""
import ast
import os

#: Roots that belong to one machine or one run, not to a checkout.
MACHINE_PREFIXES = ("/Users/", "/home/claude", "/mnt/user-data",
                    "/tmp/intake", "/tmp/wl")

SELF = os.path.basename(__file__).replace(".pyc", ".py")


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def machine_paths(directory, skip=()):
    """[(file, line, the literal)] for path literals that name one machine."""
    out = []
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".py") or name in skip or name == SELF:
            continue
        path = os.path.join(directory, name)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src, path)
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in docs
                    and any(p in node.value for p in MACHINE_PREFIXES)):
                out.append((name, node.lineno, node.value[:60]))
    return out
