from scripts.install_range import union_sessions, UNION_ROOT, report
from biology.library import Library


def test_directory_labels_and_subject_boundary():
    # Directory labels used by the public archive vary between years.
    text = '''<a href="?dir=/AS+And+A+Level/Biology+9700/2016+Jun">2016 Jun</a>
    <a href="?dir=/AS+And+A+Level/Biology+9700/May+June+2020">May June 2020</a>
    <a href="?dir=/AS+And+A+Level/Biology+9700/2022+Feb+March">2022 Feb March</a>
    <a href="?dir=/AS+And+A+Level/Biology+9700/2023+Oct+Nov">2023 Oct Nov</a>
    <a href="?dir=/AS+And+A+Level/Chemistry+9701/2023+Oct+Nov">other</a>
    <a href="https://other.example/?dir=/AS+And+A+Level/Biology+9700/2023+March">other</a>
    <a href="?dir=/AS+And+A+Level/Biology+9700/2024+March">new</a>'''
    result = union_sessions(text)
    assert set(result) == {(2016,'s'), (2020,'s'), (2022,'m'), (2023,'w')}


def test_empty_library_never_reports_success(tmp_path):
    result = report(Library(tmp_path), [2023], {'fraft':'blocked'})
    assert not result['all_discovered_files_present']
    assert not result['complete']
    assert len(result['sessions']) == 3


def test_discovered_file_is_missing_until_actual_import(tmp_path):
    lib = Library(tmp_path)
    with lib.connect() as db:
        db.execute("INSERT INTO catalog(source,original_id,filename,url) VALUES('fraft','sample','9700_s23_qp_12.pdf','https://example.org/sample.pdf')")
    result = report(lib, [2023], {})
    summer = next(s for s in result['sessions'] if s['season']=='s')
    assert summer['missing_from_listings'] == ['9700_s23_qp_12.pdf']
    assert summer['local_files'] == 0
