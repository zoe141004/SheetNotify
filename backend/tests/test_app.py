"""Smoke tests: the app imports and exposes its routes without errors."""


def test_app_imports_and_has_routes():
    import main

    paths = set()
    for route in main.app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
    # Health endpoints always present
    assert "/health" in paths
    assert "/" in paths


def test_core_services_import():
    # Ensures no circular imports / syntax errors across the change pipeline.
    import services.change_detector  # noqa: F401
    import services.change_processor  # noqa: F401
    import services.notification  # noqa: F401
    import services.poller  # noqa: F401
    import services.drive_watch  # noqa: F401
