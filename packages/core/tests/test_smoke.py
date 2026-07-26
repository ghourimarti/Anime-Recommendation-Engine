"""Smoke test for anime_core."""


def test_anime_core_imports() -> None:
    """Verify the package is importable from the workspace."""
    import anime_core

    assert anime_core is not None
