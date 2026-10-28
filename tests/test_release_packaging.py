import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from fetch_release_sources import source_index  # noqa: E402
from release import check_asset_set, check_build_info, qa_archive, validate_draft, verify_remote_tag  # noqa: E402


def test_matching_source_versions():
    index = source_index()
    assert index['qt_version'] == '6.11.2'
    assert len(index['archives']) == 5


@pytest.mark.parametrize('mutation', [
    dict(draft=False), dict(prerelease=False), dict(target_commitish='b'*40), dict(tag_name='else'),
])
def test_draft_guard_rejects_unreviewed_release(mutation):
    release = dict(draft=True, prerelease=True, tag_name='rc', target_commitish='a'*40)
    release.update(mutation)
    with pytest.raises(ValueError):
        validate_draft(release, 'rc', 'a'*40)


def test_public_repository_rejected(monkeypatch):
    monkeypatch.setattr('release.api', lambda _: {'private': False})
    with pytest.raises(ValueError, match='private'):
        verify_remote_tag('tag', 'a'*40)


def test_moved_tag_rejected(monkeypatch):
    values = iter([{'private': True}, {'sha': 'a'*40}, {'object': {'type': 'commit', 'sha': 'b'*40}}])
    monkeypatch.setattr('release.api', lambda _: next(values))
    with pytest.raises(ValueError, match='different commit'):
        verify_remote_tag('tag', 'a'*40)


def test_absent_draft_tag_allowed_but_other_errors_not(monkeypatch):
    values = iter([{'private': True}, {'sha': 'a'*40}])
    def fake(path):
        if '/git/ref/' in path:
            raise subprocess.CalledProcessError(1, ['gh'], stderr='HTTP 404: Not Found')
        return next(values)
    monkeypatch.setattr('release.api', fake)
    verify_remote_tag('tag', 'a'*40)


def test_extra_assets_fail_closed():
    with pytest.raises(ValueError):
        check_asset_set([{'name': 'expected'}, {'name': 'private-file'}], [{'name': 'expected'}])


def test_qa_archive_omits_settings_and_input_photos(tmp_path):
    import zipfile
    artifacts = tmp_path / 'artifacts'
    (artifacts / 'smoke-one/settings').mkdir(parents=True)
    (artifacts / 'smoke-one/ui.png').write_bytes(b'synthetic')
    (artifacts / 'smoke-one/result.json').write_text('{}')
    (artifacts / 'smoke-one/settings/preferences.ini').write_text('private')
    (artifacts / 'smoke-one/input.jpg').write_bytes(b'private')
    output = qa_archive(artifacts, tmp_path / 'qa.zip')
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {'smoke-one/ui.png', 'smoke-one/result.json'}


def test_dirty_build_not_releasable():
    info = dict(source_commit='a'*40, source_tree='b'*40, platform='linux', qt_runtime='6.11.2',
                application_version='1.1.2', source_dirty=True)
    with pytest.raises(ValueError):
        check_build_info(info, 'a'*40, 'b'*40, 'linux')


def test_packaged_startup_notes_do_not_instruct_bypassing_warnings():
    text = (ROOT / 'packaging/windows/README-WINDOWS.txt').read_text()
    assert 'SHA-256' in text
    assert 'Run anyway' not in text
    assert 'deliberately skipped' not in text
    replacement = (ROOT / 'packaging/LIBRARY-REPLACEMENT.txt').read_text()
    assert 'CONTACT SHEET MAKER' not in replacement
    assert 'PDF/JPEG' not in replacement


def test_distribution_tag_identifies_exact_source(monkeypatch):
    from release import validate_candidate
    def fake_git(*args):
        return 'b'*40 if args[-1] == 'HEAD^{tree}' else 'a'*40
    monkeypatch.setattr('release.git', fake_git)
    assert validate_candidate('v1.1.2', 'a'*40) == 'b'*40
    with pytest.raises(ValueError):
        validate_candidate('v1.1.1', 'a'*40)
    with pytest.raises(ValueError):
        validate_candidate('v1.1.2', 'c'*40)
