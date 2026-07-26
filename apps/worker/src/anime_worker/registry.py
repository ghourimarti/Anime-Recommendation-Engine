"""Job-type → handler registry.

The single place that maps a JobType to the function that handles it. The worker
loop dispatches by looking a message's `type` up here. An unknown type is a hard
error (→ message redelivered → DLQ), never a silent drop.
"""

from __future__ import annotations

from anime_core.jobs import JobType

from anime_worker.handlers.base import Handler
from anime_worker.handlers.feedback import handle_feedback_recorded
from anime_worker.handlers.gdpr_delete import handle_gdpr_delete
from anime_worker.handlers.housekeeping import handle_popular_precompute
from anime_worker.handlers.reembed import handle_reembed_corpus

REGISTRY: dict[JobType, Handler] = {
    JobType.FEEDBACK_RECORDED: handle_feedback_recorded,
    JobType.POPULAR_PRECOMPUTE: handle_popular_precompute,
    JobType.GDPR_DELETE: handle_gdpr_delete,
    JobType.REEMBED_CORPUS: handle_reembed_corpus,
}
