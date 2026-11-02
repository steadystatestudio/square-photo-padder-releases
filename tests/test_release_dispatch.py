import importlib.util
from pathlib import Path

import pytest


def release_module():
    path = Path(__file__).resolve().parents[1] / "scripts/release.py"
    spec = importlib.util.spec_from_file_location("release_dispatch_checks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("mutation", [
    {"GITHUB_EVENT_NAME": "push"}, {"GITHUB_REF": "refs/heads/unreviewed"},
    {"REVIEWED_COMMIT": "b" * 40}, {"GITHUB_SHA": "b" * 40},
])
def test_unreviewed_dispatch_cannot_mutate(monkeypatch, mutation):
    release = release_module()
    env = dict(GITHUB_REPOSITORY=release.REPOSITORY, GITHUB_EVENT_NAME="workflow_dispatch",
               GITHUB_REF="refs/heads/main", GITHUB_SHA="a" * 40, REVIEWED_COMMIT="a" * 40)
    for key, value in (env | mutation).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(release, "api", lambda *args: pytest.fail("No remote mutation or read expected"))
    with pytest.raises(ValueError, match="manual dispatch"):
        release.main(["init", "--tag", "v1.2.0", "--commit", "a" * 40])


def test_release_inventory_includes_later_pages(monkeypatch):
    release = release_module()
    pages = iter([[{"tag_name": f"old-{i}"} for i in range(100)], [{"tag_name": "v1.2.0"}]])
    monkeypatch.setattr(release, "api", lambda *_: next(pages))
    assert release.release_inventory()[-1]["tag_name"] == "v1.2.0"


def test_invalid_inventory_fails_closed(monkeypatch):
    release = release_module()
    monkeypatch.setattr(release, "api", lambda *_: {"message": "unavailable"})
    with pytest.raises(ValueError, match="Invalid release inventory"):
        release.release_inventory()


def test_duplicate_tag_blocks_selected_draft(monkeypatch):
    from types import SimpleNamespace
    release = release_module()
    item = dict(id=123, draft=True, prerelease=True, tag_name='v1.2.0',
                target_commitish='a' * 40, assets=[])
    args = SimpleNamespace(release_id='123', tag='v1.2.0', commit='a' * 40)
    monkeypatch.setattr(release, 'api', lambda *_: item)
    monkeypatch.setattr(release, 'release_inventory', lambda: [item, item | {'id': 456}])
    monkeypatch.setattr(release.time, 'sleep', lambda _: pytest.fail('Ambiguous drafts must fail immediately'))
    with pytest.raises(ValueError, match='uniquely'):
        release.current_release(args)


@pytest.mark.parametrize('repository', [
    'steadystatestudio/square-photo-padder-releases',
    'steadystatestudio/square-photo-padder-builds',
])
def test_exact_reviewed_repository_routes_are_accepted(monkeypatch, repository):
    monkeypatch.setenv('GITHUB_REPOSITORY', repository)
    release = release_module()
    for key, value in dict(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                           GITHUB_SHA='a'*40, REVIEWED_COMMIT='a'*40).items():
        monkeypatch.setenv(key, value)
    staged = []
    monkeypatch.setattr(release, 'init', lambda args: staged.append(args.commit))
    assert release.main(['init', '--tag', 'v1.2.2', '--commit', 'a'*40]) == 0
    assert release.REPOSITORY == repository
    assert staged == ['a'*40]


def test_other_repository_is_rejected_before_any_remote_operation(monkeypatch):
    monkeypatch.setenv('GITHUB_REPOSITORY', 'someone/else')
    release = release_module()
    for key, value in dict(GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                           GITHUB_SHA='a'*40, REVIEWED_COMMIT='a'*40).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(release, 'api', lambda *_: pytest.fail('No remote operation expected'))
    with pytest.raises(ValueError, match='manual dispatch'):
        release.main(['init', '--tag', 'v1.2.2', '--commit', 'a'*40])


def test_build_repository_must_remain_private(monkeypatch):
    repository = 'steadystatestudio/square-photo-padder-builds'
    monkeypatch.setenv('GITHUB_REPOSITORY', repository)
    release = release_module()
    reads = []
    def api(path):
        reads.append(path)
        return dict(full_name=repository, private=False)
    monkeypatch.setattr(release, 'api', api)
    with pytest.raises(ValueError, match='remain private'):
        release.verify_remote_tag('v1.2.2', 'a'*40)
    assert reads == ['repos/' + repository]


def test_new_draft_list_visibility_retries_read_only(monkeypatch):
    from types import SimpleNamespace
    release = release_module()
    item = dict(id=123, draft=True, prerelease=True, tag_name='v1.2.2',
                target_commitish='a' * 40, assets=[])
    args = SimpleNamespace(release_id='123', tag='v1.2.2', commit='a' * 40)
    reads, sleeps = [], []
    def api(path):
        reads.append(path)
        assert path.endswith('/releases/123')
        return item
    pages = iter([[], [], [item]])
    monkeypatch.setattr(release, 'api', api)
    monkeypatch.setattr(release, 'release_inventory', lambda: next(pages))
    monkeypatch.setattr(release.time, 'sleep', sleeps.append)
    assert release.current_release(args) == item
    assert len(reads) == 3
    assert sleeps == [1, 2]


def test_new_draft_visibility_retries_are_bounded(monkeypatch):
    from types import SimpleNamespace
    release = release_module()
    item = dict(id=123, draft=True, prerelease=True, tag_name='v1.2.2',
                target_commitish='a' * 40, assets=[])
    args = SimpleNamespace(release_id='123', tag='v1.2.2', commit='a' * 40)
    sleeps = []
    monkeypatch.setattr(release, 'api', lambda *_: item)
    monkeypatch.setattr(release, 'release_inventory', lambda: [])
    monkeypatch.setattr(release.time, 'sleep', sleeps.append)
    with pytest.raises(ValueError, match='after visibility retries'):
        release.current_release(args)
    assert sleeps == [1, 2, 4, 8]


def test_wrong_selected_release_id_does_not_retry(monkeypatch):
    from types import SimpleNamespace
    release = release_module()
    item = dict(id=123, draft=True, prerelease=True, tag_name='v1.2.2',
                target_commitish='a' * 40, assets=[])
    args = SimpleNamespace(release_id='123', tag='v1.2.2', commit='a' * 40)
    monkeypatch.setattr(release, 'api', lambda *_: item)
    monkeypatch.setattr(release, 'release_inventory', lambda: [item | {'id': 456}])
    monkeypatch.setattr(release.time, 'sleep', lambda _: pytest.fail('Wrong ID must fail immediately'))
    with pytest.raises(ValueError, match='uniquely'):
        release.current_release(args)


@pytest.mark.parametrize('mutation', [dict(draft=False), dict(target_commitish='b' * 40)])
def test_draft_state_change_during_visibility_wait_fails_closed(monkeypatch, mutation):
    from types import SimpleNamespace
    release = release_module()
    item = dict(id=123, draft=True, prerelease=True, tag_name='v1.2.2',
                target_commitish='a' * 40, assets=[])
    args = SimpleNamespace(release_id='123', tag='v1.2.2', commit='a' * 40)
    reads = iter([item, item | mutation])
    sleeps = []
    monkeypatch.setattr(release, 'api', lambda *_: next(reads))
    monkeypatch.setattr(release, 'release_inventory', lambda: [])
    monkeypatch.setattr(release.time, 'sleep', sleeps.append)
    with pytest.raises(ValueError, match='selected exact-commit draft'):
        release.current_release(args)
    assert sleeps == [1]


def test_stale_draft_detail_cannot_override_published_list_entry(monkeypatch):
    from types import SimpleNamespace
    release = release_module()
    item = dict(id=123, draft=True, prerelease=True, tag_name='v1.2.2',
                target_commitish='a' * 40, assets=[])
    args = SimpleNamespace(release_id='123', tag='v1.2.2', commit='a' * 40)
    monkeypatch.setattr(release, 'api', lambda *_: item)
    monkeypatch.setattr(release, 'release_inventory', lambda: [item | {'draft': False}])
    monkeypatch.setattr(release.time, 'sleep', lambda _: pytest.fail('Published draft must fail immediately'))
    with pytest.raises(ValueError, match='selected exact-commit draft'):
        release.current_release(args)
