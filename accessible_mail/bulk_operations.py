from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .models import MessageSummary


def run_bulk_operations(
    summaries: list[MessageSummary],
    operation: Callable[[MessageSummary], None],
    max_workers: int = 4,
) -> tuple[list[MessageSummary], list[tuple[MessageSummary, Exception]]]:
    if not summaries:
        return [], []
    worker_count = max(1, min(max_workers, len(summaries)))
    succeeded: list[MessageSummary] = []
    failed: list[tuple[MessageSummary, Exception]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        jobs = [(summary, executor.submit(operation, summary)) for summary in summaries]
        for summary, job in jobs:
            try:
                job.result()
            except Exception as exc:
                failed.append((summary, exc))
            else:
                succeeded.append(summary)
    return succeeded, failed
