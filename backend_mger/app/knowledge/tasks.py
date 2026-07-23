from __future__ import annotations

from uuid import UUID

from app.celery_app import celery_app
from app.db import SessionLocal
from app.knowledge.publisher import KnowledgePublisher
from app.knowledge.workflow import KnowledgeBuildWorkflow
from app.models import BackgroundJob


@celery_app.task(
    bind=True,
    name="knowledge.build",
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_knowledge_build(self, run_id: str) -> dict:
    result = KnowledgeBuildWorkflow().run(UUID(run_id))
    return {"build_run_id": run_id, "metrics": result.get("metrics", {}), "review_count": result.get("review_count", 0)}


@celery_app.task(
    bind=True,
    name="knowledge.publish",
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_knowledge_build(self, publication_id: str, job_id: str) -> dict:
    counts = KnowledgePublisher().publish(UUID(publication_id), UUID(job_id))
    return {"publication_id": publication_id, **counts}


def dispatch_background_job(job_id: UUID) -> str:
    with SessionLocal() as db:
        job = db.get(BackgroundJob, job_id)
        if job is None:
            raise LookupError("后台任务不存在")
        if job.status != "queued":
            raise ValueError("仅排队中的后台任务可以分发")
        payload = dict(job.payload)
        if job.job_type == "knowledge_build":
            result = execute_knowledge_build.apply_async(args=[str(payload["build_run_id"])], task_id=str(job.id))
        elif job.job_type == "knowledge_publish":
            result = publish_knowledge_build.apply_async(
                args=[str(payload["publication_id"]), str(job.id)],
                task_id=str(job.id),
            )
        else:
            raise ValueError(f"任务类型 {job.job_type} 没有可用执行器")
        return str(result.id)
