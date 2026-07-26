"""Smoke test for anime_retrieval."""


def test_anime_retrieval_imports() -> None:
    """Verify the package is importable from the workspace."""
    import anime_retrieval

    assert anime_retrieval is not None
