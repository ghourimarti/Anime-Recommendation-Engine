def test_anime_worker_imports() -> None:
    import anime_worker
    import anime_worker.worker  # noqa: F401

    # All four job types are wired to a handler.
    from anime_core.jobs import JobType
    from anime_worker.registry import REGISTRY

    assert set(REGISTRY) == set(JobType)
