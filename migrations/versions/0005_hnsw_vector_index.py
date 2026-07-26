"""Add an HNSW index on anime_chunks.embedding.

Without it, every dense retrieval is a sequential scan. Verified with EXPLAIN
(ANALYZE) on the live database:

    Limit  (actual time=1.910..1.912 rows=20)
      ->  Sort  (Sort Method: top-N heapsort)
            ->  Seq Scan on anime_chunks  (actual rows=269)   <-- reads EVERY row
                  Buffers: shared hit=887

Postgres reads every embedding, computes 269 cosine distances, then sorts. At 269
chunks that costs 1.9ms and looks perfectly healthy, which is exactly why this
kind of bug survives: the plan is O(n) and the corpus is small, so nothing hurts
until it suddenly does. Ten thousand titles is ~40k chunks and the same query
becomes hundreds of milliseconds of pure CPU, per request, before the reranker or
the LLM has done anything at all.

HNSW, not IVFFlat:
  - IVFFlat must be built on data that already exists (it clusters into lists), so
    it has to be rebuilt after a bulk re-ingest and behaves badly when the table
    is empty at migration time — which is precisely our situation, since 0002
    empties the column and ingest repopulates it afterwards.
  - HNSW builds incrementally, needs no training, and gives better
    recall-at-latency. It costs more to build and more memory; for a
    read-dominated corpus refreshed occasionally, that is the right trade.

vector_cosine_ops matches the `<=>` operator the query actually uses
(PgvectorIndex.search → ORMChunk.embedding.cosine_distance). An index built with
the wrong opclass is simply never used, and Postgres will not warn you: you get a
seq scan and a good night's sleep.

HNSW is APPROXIMATE. It trades exactness for speed, so recall is not guaranteed to
be 100% and retrieval results can shift. That is not a detail to wave through — it
is a quality change — so the golden-set eval gate is the check that it did not cost
us anything measurable.

Production note: CREATE INDEX takes an ACCESS EXCLUSIVE lock and blocks writes for
the duration of the build. On a large table use CREATE INDEX CONCURRENTLY, which
cannot run inside a transaction and therefore cannot run in a normal Alembic
migration (it needs an autocommit connection). See docs/runbooks for the online
index-build procedure. At this corpus size the plain build is a sub-second lock.

Revision ID: 0005_hnsw_vector_index
Revises:     0004_account_deletions
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_hnsw_vector_index"
down_revision: str | None = "0004_account_deletions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# m               = edges per node. Higher = better recall, bigger index, slower build.
# ef_construction = candidate list size while building. Higher = better graph quality.
# 16 / 64 are pgvector's defaults and the right starting point: tune only against
# measured recall on the golden set, never by taste.
HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64


def upgrade() -> None:
    # The build is memory-hungry; the default 64MB maintenance_work_mem makes it
    # spill to disk and crawl. Set it for this session only.
    op.execute("SET maintenance_work_mem = '512MB'")
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_anime_chunks_embedding_hnsw
        ON anime_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_anime_chunks_embedding_hnsw")
