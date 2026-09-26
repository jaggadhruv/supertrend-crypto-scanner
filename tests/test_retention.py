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


def test_index_is_not_counted_and_survives(tmp_path):
    (tmp_path / "index.html").write_text("site root")
    for day in range(1, 35):
        (tmp_path / f"{settings.REPORT_PREFIX}2026-10-{day:02d}.html").write_text("x") if day <= 31 else None
    state.cleanup_reports(keep=30, folder=tmp_path)
    assert (tmp_path / "index.html").exists()
    assert len(list(tmp_path.glob(f"{settings.REPORT_PREFIX}*.html"))) == 30


def test_build_index_inserts_archive_after_topbar():
    import report
    page = ('<body><div class="wrap">\n\n  <div class="topbar">\n    <h1>T</h1>\n'
            '    <div class="params">p</div>\n  </div>\n\n  <div class="panel">x</div>')
    names = [f"{settings.REPORT_PREFIX}2026-10-0{d}.html" for d in (1, 2, 3)]
    out = report.build_index(page, names)
    assert out.index("archive-bar") > out.index("topbar") and out.index("archive-bar") < out.index('class="panel"')
    assert out.index("2026-10-03") < out.index("2026-10-01")          # newest first
