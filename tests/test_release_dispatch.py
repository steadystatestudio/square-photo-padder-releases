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
    with pytest.raises(ValueError, match='uniquely'):
        release.current_release(args)
