from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NAV_FILES = [Path("src/core/nav.py"), Path("src/core/navigation.py")]


def _menu_texts() -> set[str]:
    texts: set[str] = set()
    for rel in NAV_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "KeyboardButton"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                texts.add(node.args[0].value)
    return texts


def _handled_texts() -> set[str]:
    handled: set[str] = set()
    for path in (REPO_ROOT / "src").rglob("*.py"):
        if any(part in {"nav.py", "navigation.py"} for part in path.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or not node.ops or not isinstance(node.ops[0], ast.Eq):
                continue
            left = node.left
            if (
                isinstance(left, ast.Attribute)
                and left.attr == "text"
                and isinstance(left.value, ast.Name)
                and left.value.id == "F"
            ):
                for comp in node.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        handled.add(comp.value)
    return handled


def test_reply_buttons_have_handlers() -> None:
    menu = _menu_texts()
    handled = _handled_texts()
    missing = sorted(menu - handled)
    assert not missing, f"ReplyKeyboard buttons без F.text-хэндлера: {missing}"
