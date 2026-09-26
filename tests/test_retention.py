"""Report retention: only the newest N files survive, by date in the file name."""
import settings
import state


def test_keeps_newest_30(tmp_path):
    for day in range(1, 41):
        (tmp_path / f"{settings.REPORT_PREFIX}2026-08-{day:02d}.html").write_text("x") if day <= 31 else \
            (tmp_path / f"{settings.REPORT_PREFIX}2026-09-{day - 31:02d}.html").write_text("x")
    (tmp_path / "notes.txt").write_text("not a report")
    deleted = state.cleanup_reports(keep=30, folder=tmp_path)
    left = sorted(p.name for p in tmp_path.glob("*.html"))
    assert len(left) == 30 and len(deleted) == 10
    assert left[0] == f"{settings.REPORT_PREFIX}2026-08-11.html"      # 10 oldest gone
    assert left[-1] == f"{settings.REPORT_PREFIX}2026-09-09.html"     # newest kept
    assert (tmp_path / "notes.txt").exists()                            # other files untouched


def test_nothing_deleted_under_limit(tmp_path):
    for day in range(1, 6):
        (tmp_path / f"{settings.REPORT_PREFIX}2026-09-{day:02d}.html").write_text("x")
    assert state.cleanup_reports(keep=30, folder=tmp_path) == []
