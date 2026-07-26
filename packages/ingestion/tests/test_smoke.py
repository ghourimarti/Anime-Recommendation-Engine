"""Smoke test for anime_ingestion."""


def test_anime_ingestion_imports() -> None:
    """Verify the package is importable from the workspace."""
    import anime_ingestion

    assert anime_ingestion is not None
