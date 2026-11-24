"""Стражи правил архитектуры (docs/architecture.md → Транзакции)."""

import re
from pathlib import Path

SERVICES = Path(__file__).resolve().parent.parent / "src" / "tickets" / "services"


def test_services_never_commit_or_rollback():
    """Транзакцию завершает граница (unit_of_work), а не сервис."""
    offenders = [
        f"{path.name}:{n}: {line.strip()}"
        for path in sorted(SERVICES.glob("*.py"))
        for n, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"\.(commit|rollback)\(", line)
    ]
    assert offenders == []
