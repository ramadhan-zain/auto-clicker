from autoclick import macos


def test_accessibility_check_returns_bool():
    assert isinstance(macos.accessibility_granted(), bool)


def test_frontmost_bundle_id_is_a_bundle_id_or_none():
    bundle_id = macos.frontmost_bundle_id()

    assert bundle_id is None or "." in bundle_id


def test_windowed_apps_are_named_unique_and_sorted():
    apps = macos.windowed_apps()

    assert all(app.name and app.bundle_id for app in apps)
    assert len({app.bundle_id for app in apps}) == len(apps)
    assert [app.name.lower() for app in apps] == sorted(app.name.lower() for app in apps)
