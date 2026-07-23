"""Import the five approved Markdown documents into the knowledge source registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.knowledge.service import KnowledgeService
from app.knowledge.tasks import dispatch_background_job


DEFAULT_DOCUMENTS = (
    Path(r"C:\Users\w\Desktop\mrakdown文档\data\05_qa_ready_md\实用养蚕技术200问.md"),
    Path(r"C:\Users\w\Desktop\mrakdown文档\data\05_qa_ready_md\简明养蚕手册.md"),
    Path(r"C:\Users\w\Desktop\mrakdown文档\data\05_qa_ready_md\中国养蚕学.md"),
    Path(r"C:\Users\w\Desktop\mrakdown文档\data\05_qa_ready_md\家蚕病理学.md"),
    Path(r"C:\Users\w\Desktop\mrakdown文档\data\05_qa_ready_md\常见蚕病防治.md"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, nargs="*", default=list(DEFAULT_DOCUMENTS))
    parser.add_argument(
        "--directory",
        type=Path,
        help="Import every Markdown file from this directory; overrides --documents.",
    )
    parser.add_argument("--version", default="initial-2026-07-20")
    parser.add_argument("--enqueue", action="store_true", help="Import 后立即创建 RAG+KG 构建任务")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    documents = args.documents
    if args.directory is not None:
        if not args.directory.is_dir():
            raise FileNotFoundError(str(args.directory))
        documents = sorted(
            path
            for path in args.directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".markdown"}
        )
        if not documents:
            raise FileNotFoundError(f"目录中没有 Markdown 文档：{args.directory}")
    missing = [str(path) for path in documents if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少首批文献：" + "、".join(missing))

    output: list[dict] = []
    queued_job_ids = []
    with SessionLocal() as db:
        service = KnowledgeService(db)
        for path in documents:
            source, version, created = service.import_path(
                path,
                title=path.stem,
                version=args.version,
                license_note="用户提供的首批养蚕领域真实文献，仅用于本项目知识库构建。",
            )
            item = {
                "source_id": str(source.id),
                "source_version_id": str(version.id),
                "title": source.title,
                "sha256": version.content_sha256,
                "created": created,
                "status": version.status,
            }
            if args.enqueue:
                run, job, build_created = service.queue_build(
                    source.id,
                    targets=["rag", "kg"],
                    requested_by_id=None,
                )
                item["build_run_id"] = str(run.id)
                item["job_id"] = str(job.id)
                item["build_created"] = build_created
                if build_created:
                    queued_job_ids.append(job.id)
            output.append(item)

    for job_id in queued_job_ids:
        dispatch_background_job(job_id)
    print(json.dumps({"items": output, "queued": len(queued_job_ids)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
