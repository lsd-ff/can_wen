"""Validate the real MinerU upload and Markdown conversion path safely."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import uuid
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete

from app.config import Settings
from app.db import SessionLocal
from app.knowledge.markdown import AdaptiveMarkdownChunker
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import KnowledgeStorage
from app.knowledge.workflow import KnowledgeBuildWorkflow
from app.models import KnowledgeSource, KnowledgeSourceVersion


HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="A small PDF/Word/image file to parse")
    parser.add_argument("--expect", action="append", default=[], help="Text that must occur in full.md")
    parser.add_argument("--output", type=Path, help="Optional path to retain the parsed Markdown")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.file.resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    settings = Settings()
    storage = KnowledgeStorage(settings)
    marker = uuid.uuid4().hex[:12]
    source_id: UUID | None = None
    version_id: UUID | None = None
    storage_uris: set[str] = set()

    try:
        with SessionLocal() as db:
            source, version, created = KnowledgeService(db, settings=settings, storage=storage).import_path(
                source_path,
                title=f"MinerU API 验收-{marker}",
                version=f"smoke-{marker}",
                license_note="隔离的 MinerU API 验收数据，完成后自动清理",
                origin="mineru_smoke",
            )
            if not created:
                raise RuntimeError("MinerU 验收知识源意外重复")
            source_id = source.id
            version_id = version.id
            storage_uris.add(version.original_storage_uri)

        workflow = KnowledgeBuildWorkflow(settings=settings, storage=storage)
        markdown_uri = asyncio.run(workflow._parse_with_mineru(version_id))
        markdown = storage.read_text(markdown_uri)

        with SessionLocal() as db:
            version = db.get(KnowledgeSourceVersion, version_id)
            if version is None:
                raise LookupError("MinerU 验收版本记录不存在")
            parser_metadata = dict(version.parser_metadata)
            if version.status != "parsed" or version.parser != "mineru_v4":
                raise RuntimeError("MinerU 解析状态未正确持久化")
            if version.markdown_storage_uri:
                storage_uris.add(version.markdown_storage_uri)
            result_zip_uri = parser_metadata.get("result_zip_uri")
            if result_zip_uri:
                storage_uris.add(str(result_zip_uri))

        missing = [expected for expected in args.expect if expected not in markdown]
        if missing:
            raise RuntimeError(f"MinerU Markdown 缺少预期文本：{missing}")
        headings = HEADING_RE.findall(markdown)
        table_rows = MARKDOWN_TABLE_RE.findall(markdown)
        has_html_table = "<table" in markdown.lower()
        if not headings:
            raise RuntimeError("MinerU Markdown 未保留任何标题结构")
        if len(table_rows) < 2 and not has_html_table:
            raise RuntimeError("MinerU Markdown 未保留表格结构")

        chunks = AdaptiveMarkdownChunker(settings.knowledge_chunk_target_tokens).split(markdown)
        if not chunks:
            raise RuntimeError("MinerU Markdown 无法进入自适应切分器")
        if args.output:
            output = args.output.resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown, encoding="utf-8")

        print(
            json.dumps(
                {
                    "status": "passed",
                    "batch_id": parser_metadata.get("batch_id"),
                    "model_version": parser_metadata.get("model_version"),
                    "markdown_chars": len(markdown),
                    "heading_count": len(headings),
                    "table_row_count": len(table_rows),
                    "html_table": has_html_table,
                    "chunk_count": len(chunks),
                    "expected_text_count": len(args.expect),
                    "expected_text_preserved": True,
                },
                ensure_ascii=False,
            )
        )
    finally:
        if version_id is not None:
            with suppress(Exception):
                with SessionLocal() as db:
                    version = db.get(KnowledgeSourceVersion, version_id)
                    if version:
                        if version.markdown_storage_uri:
                            storage_uris.add(version.markdown_storage_uri)
                        result_zip_uri = dict(version.parser_metadata).get("result_zip_uri")
                        if result_zip_uri:
                            storage_uris.add(str(result_zip_uri))
        if source_id is not None:
            with suppress(Exception):
                with SessionLocal() as db:
                    db.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_id))
                    db.commit()
        for uri in storage_uris:
            with suppress(Exception):
                storage.delete(uri)


if __name__ == "__main__":
    main()
