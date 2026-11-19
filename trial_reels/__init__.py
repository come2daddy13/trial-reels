"""Trial reels: planer i montaż próbnych rolek na Instagramie."""
from pathlib import Path


def _read_version(path: Path) -> str:
    """Numer wersji z pliku VERSION. Gdy pliku brak, zwraca 0.0.0, żeby komendy (też aktualizacja) dalej działały."""
    try:
        return path.read_text(encoding="utf-8-sig").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


VERSION = _read_version(Path(__file__).resolve().parents[1] / "VERSION")
