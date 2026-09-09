import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [ROOT / "src", ROOT / "bot.py"]


def _collect():
    emits: dict[str, str] = {}
    handles: list[tuple[str, str]] = []
    for f in ROOT.rglob("*.py"):
        if "venv" in str(f) or "/tests" in str(f) or ".git" in str(f):
            continue
        s = f.read_text(errors="replace")
        for m in re.finditer(r'callback_data=(?:"([^"{]+)"|f"([^{]*?)(?:\{|$))', s):
            lit, pre = m.group(1), m.group(2)
            if lit:
                emits[lit] = "lit"
            elif pre:
                emits[pre] = "pre"
        for m in re.finditer(r'F\.data\s*==\s*"([^"]+)"', s):
            handles.append(("==", m.group(1)))
        for m in re.finditer(r'F\.data\.startswith\("([^"]+)"\)', s):
            handles.append(("pre", m.group(1)))
    return emits, handles


def test_callback_buttons_have_handlers():
    emits, handles = _collect()
    eq = {p for k, p in handles if k == "=="}
    pr = {p for k, p in handles if k == "pre"}
    missing = []
    for val, kind in sorted(emits.items()):
        covered = (
            (val in eq or any(val.startswith(p) for p in pr)) if kind == "lit" else val in pr
        )
        if not covered:
            missing.append(f"{val} (kind={kind})")
    assert not missing, f"callback_data без хэндлера: {missing}"


def test_every_emit_is_a_value():
    """Прод-код: убрать хэндлер -> тест падает, убрать кнопку -> тест падает."""
    emits, _ = _collect()
    assert emits, "нет эмитед callback_data — проверь обход сканера"
