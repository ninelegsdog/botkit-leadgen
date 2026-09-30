import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = [ROOT / "bot.py", ROOT / "src" / "bot.py"]
COMPOSE = ROOT / "deploy" / "compose.yml"


def _entrypoint() -> Path:
    found = [p for p in ENTRYPOINTS if p.exists()]
    assert len(found) == 1, f"ожидалась ровно одна точка входа бота: {found}"
    return found[0]


def _prod_sources() -> list[Path]:
    out = []
    for f in ROOT.rglob("*.py"):
        s = str(f)
        if "venv" in s or f"{os.sep}tests{os.sep}" in s or ".git" in s:
            continue
        out.append(f)
    return out


def test_set_webhook_is_never_given_a_certificate():
    """Прод-код: вернуть `certificate=cert` в setWebhook -> тест падает."""
    src = _entrypoint().read_text()
    calls = re.findall(r"set_webhook\((?:[^()]|\([^()]*\))*\)", src, re.S)
    assert calls, "set_webhook не найден — сканер проверяет пустоту"
    pinned = [c for c in calls if "certificate" in c]
    assert not pinned, f"setWebhook получает certificate — вернётся пин: {pinned}"


def test_no_certificate_loader_remains():
    """Прод-код: вернуть _load_cert() -> тест падает."""
    leftovers = [
        str(f.relative_to(ROOT)) for f in _prod_sources()
        if "_load_cert" in f.read_text(errors="replace")
    ]
    assert not leftovers, f"загрузчик сертификата снова в коде: {leftovers}"


def test_no_webhook_cert_path_setting():
    """Прод-код: вернуть поле webhook_cert_path -> тест падает."""
    hits = [
        str(f.relative_to(ROOT)) for f in _prod_sources()
        if re.search(r"webhook_cert_path|WEBHOOK_CERT_PATH", f.read_text(errors="replace"))
    ]
    assert not hits, f"настройка webhook_cert_path снова в коде: {hits}"


def test_compose_does_not_hand_the_bot_a_certificate():
    """Прод-код: вернуть env WEBHOOK_CERT_PATH или mount certs/ -> тест падает."""
    text = COMPOSE.read_text()
    assert "WEBHOOK_CERT_PATH" not in text, "compose снова передаёт WEBHOOK_CERT_PATH боту"
    cert_mounts = [
        line for line in text.splitlines()
        if line.strip().startswith("- ") and re.search(r"certs|fullchain|\.pem", line)
    ]
    assert not cert_mounts, f"compose снова монтирует сертификат в бота: {cert_mounts}"
