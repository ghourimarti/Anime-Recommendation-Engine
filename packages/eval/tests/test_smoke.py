"""Smoke test for anime_eval."""


def test_anime_eval_imports() -> None:
    """Verify the package is importable from the workspace."""
    import anime_eval

    assert anime_eval is not None
