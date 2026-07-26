"""Smoke test for anime_api."""


def test_anime_api_imports() -> None:
    """Verify the package is importable from the workspace."""
    import anime_api

    assert anime_api is not None
