from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import hashlib
import mimetypes
import re
import uuid
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.security import now_utc
from app.models import (
    Conversation,
    Farm,
    HusbandryCase,
    HusbandryCaseFollowUp,
    HusbandryDailyRecord,
    HusbandryRecordAsset,
    Message,
    Project,
    SilkwormBatch,
    UploadedFile,
    User,
)
from app.schemas.husbandry import (
    BatchResponse,
    CaseFollowUpResponse,
    HusbandryAssetResponse,
    HusbandryExpertReviewResponse,
    CaseResponse,
    DailyRecordResponse,
    FarmResponse,
    HusbandryDashboardResponse,
)
from app.services.storage_service import delete_object_file, upload_object_file


@dataclass(frozen=True)
class HusbandryAttachmentUpload:
    file_name: str
    content_type: str
    content: bytes


def list_current_user_farms(db: Session, *, user: User, include_archived: bool = False) -> list[FarmResponse]:
    query = select(Farm).where(Farm.owner_id == user.id)
    if not include_archived:
        query = query.where(Farm.status == "active")
    farms = db.scalars(query.order_by(desc(Farm.updated_at), desc(Farm.created_at))).all()
    return [_farm_response(farm) for farm in farms]


def create_current_user_farm(
    db: Session,
    *,
    user: User,
    name: str,
    location: str | None,
    notes: str | None,
) -> FarmResponse:
    farm = Farm(
        owner_id=user.id,
        name=name.strip(),
        location=_optional_text(location),
        notes=_optional_text(notes),
        status="active",
    )
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return _farm_response(farm)


def update_current_user_farm(db: Session, *, user: User, farm_id: UUID, values: dict[str, Any]) -> FarmResponse:
    farm = _get_owned_farm(db, user=user, farm_id=farm_id)
    for field, value in values.items():
        setattr(farm, field, _optional_text(value) if field in {"name", "location", "notes"} else value)
    farm.updated_at = now_utc()
    db.add(farm)
    db.commit()
    db.refresh(farm)
    return _farm_response(farm)


def list_current_user_batches(db: Session, *, user: User, farm_id: UUID | None = None, include_archived: bool = False) -> list[BatchResponse]:
    query = (
        select(SilkwormBatch, Farm.name)
        .join(Farm, SilkwormBatch.farm_id == Farm.id)
        .where(Farm.owner_id == user.id)
        .order_by(desc(SilkwormBatch.start_date), desc(SilkwormBatch.created_at))
    )
    if farm_id is not None:
        query = query.where(SilkwormBatch.farm_id == farm_id)
    if not include_archived:
        query = query.where(Farm.status == "active", SilkwormBatch.status != "archived")
    rows = db.execute(query).all()
    return [_batch_response(batch, farm_name) for batch, farm_name in rows]


def create_current_user_batch(
    db: Session,
    *,
    user: User,
    farm_id: UUID,
    project_id: UUID | None,
    batch_code: str | None,
    variety: str | None,
    instar: str | None,
    start_date: date | None,
    expected_cocooning_date: date | None,
    population_count: int | None,
    notes: str | None,
) -> BatchResponse:
    farm = _get_owned_farm(db, user=user, farm_id=farm_id)
    if project_id is not None:
        _get_owned_project(db, user=user, project_id=project_id)
    batch = SilkwormBatch(
        farm_id=farm.id,
        project_id=project_id,
        batch_code=_optional_text(batch_code),
        variety=_optional_text(variety),
        instar=_optional_text(instar),
        start_date=start_date,
        expected_cocooning_date=expected_cocooning_date,
        population_count=population_count,
        notes=_optional_text(notes),
        status="active",
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_response(batch, farm.name)


def update_current_user_batch(db: Session, *, user: User, batch_id: UUID, values: dict[str, Any]) -> BatchResponse:
    batch = _get_owned_batch(db, user=user, batch_id=batch_id)
    for field, value in values.items():
        setattr(batch, field, _optional_text(value) if field in {"batch_code", "variety", "instar", "notes"} else value)
    batch.updated_at = now_utc()
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_response(batch, _farm_name(db, batch.farm_id))


def list_current_user_daily_records(
    db: Session,
    *,
    user: User,
    batch_id: UUID,
) -> list[DailyRecordResponse]:
    _get_owned_batch(db, user=user, batch_id=batch_id)
    records = db.scalars(
        select(HusbandryDailyRecord)
        .where(HusbandryDailyRecord.batch_id == batch_id)
        .order_by(desc(HusbandryDailyRecord.record_date), desc(HusbandryDailyRecord.created_at))
    ).all()
    asset_map = _assets_by_owner_ids(db, daily_record_ids=[record.id for record in records])
    return [_daily_record_response(record, assets=asset_map["daily"].get(record.id, [])) for record in records]


def upsert_current_user_daily_record(
    db: Session,
    *,
    user: User,
    batch_id: UUID,
    values: dict[str, Any],
) -> DailyRecordResponse:
    _get_owned_batch(db, user=user, batch_id=batch_id)
    record = db.scalar(
        select(HusbandryDailyRecord).where(
            HusbandryDailyRecord.batch_id == batch_id,
            HusbandryDailyRecord.record_date == values["record_date"],
        )
    )
    if record is None:
        record = HusbandryDailyRecord(batch_id=batch_id, **values)
        db.add(record)
    else:
        for field, value in values.items():
            setattr(record, field, value)
        db.add(record)
    db.commit()
    db.refresh(record)
    return _daily_record_response(record)


def delete_current_user_daily_record(db: Session, *, user: User, batch_id: UUID, record_id: UUID) -> None:
    _get_owned_batch(db, user=user, batch_id=batch_id)
    record = db.scalar(select(HusbandryDailyRecord).where(HusbandryDailyRecord.id == record_id, HusbandryDailyRecord.batch_id == batch_id))
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="每日记录不存在")
    _delete_record_assets(db, owner_id=user.id, daily_record_id=record.id)
    db.delete(record)
    db.commit()


def list_current_user_cases(
    db: Session,
    *,
    user: User,
    batch_id: UUID | None = None,
    case_status: str | None = None,
) -> list[CaseResponse]:
    query = (
        select(HusbandryCase, Farm.name, SilkwormBatch.batch_code)
        .join(Farm, HusbandryCase.farm_id == Farm.id)
        .outerjoin(SilkwormBatch, HusbandryCase.batch_id == SilkwormBatch.id)
        .where(HusbandryCase.owner_id == user.id)
        .order_by(desc(HusbandryCase.occurred_on), desc(HusbandryCase.updated_at))
    )
    if batch_id is not None:
        query = query.where(HusbandryCase.batch_id == batch_id)
    if case_status is not None:
        query = query.where(HusbandryCase.status == case_status)
    rows = db.execute(query).all()
    follow_up_map = _follow_ups_by_case_id(db, [case.id for case, _, _ in rows])
    review_map = _published_expert_reviews_by_case_id(db, [case.id for case, _, _ in rows])
    asset_map = _assets_by_owner_ids(db, case_ids=[case.id for case, _, _ in rows])
    return [
        _case_response(case, farm_name, batch_code, follow_up_map.get(case.id, []), review_map.get(case.id, []), asset_map["case"].get(case.id, []))
        for case, farm_name, batch_code in rows
    ]


def create_current_user_case(
    db: Session,
    *,
    user: User,
    values: dict[str, Any],
) -> CaseResponse:
    if values.get("status", "needs_more_info") not in {"needs_more_info", "suspected"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="新建病例只能标记为待补充或疑似，处理中和结案由复核流程管理")
    if any(_optional_text(values.get(field)) for field in {"diagnosis_summary", "recommendation"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="专家结论和处置建议只能由管理员发布")
    values["diagnosis_summary"] = None
    values["recommendation"] = None
    farm = _get_owned_farm(db, user=user, farm_id=values["farm_id"])
    batch_id = values.get("batch_id")
    if batch_id is not None:
        batch = _get_owned_batch(db, user=user, batch_id=batch_id)
        if batch.farm_id != farm.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="病例批次不属于所选养殖场")
    project_id = values.get("project_id")
    if project_id is not None:
        _get_owned_project(db, user=user, project_id=project_id)

    source_snapshot: dict[str, Any] = {}
    source_conversation_id = values.get("source_conversation_id")
    if source_conversation_id is not None:
        conversation = _get_owned_conversation(db, user=user, conversation_id=source_conversation_id)
        source_snapshot = _conversation_snapshot(db, conversation=conversation)
        if project_id is None:
            values["project_id"] = conversation.project_id

    case = HusbandryCase(owner_id=user.id, source_snapshot=source_snapshot, **values)
    db.add(case)
    db.commit()
    db.refresh(case)
    return _case_response(case, farm.name, _batch_code(db, case.batch_id), [])


def update_current_user_case(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    values: dict[str, Any],
) -> CaseResponse:
    case = _get_owned_case(db, user=user, case_id=case_id)
    if not values:
        return _case_response(case, _farm_name(db, case.farm_id), _batch_code(db, case.batch_id), _follow_ups_by_case_id(db, [case.id]).get(case.id, []))

    if case.status == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例已结案，不能再修改")
    protected_fields = {"severity", "diagnosis_summary", "recommendation"}
    if protected_fields.intersection(values):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="风险等级、专家结论和处置建议由系统与专家复核流程维护")
    if "status" in values:
        if values["status"] != "closed":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="病例状态由复核流程维护；用户只能在满足条件后结案")
        _require_user_case_closure_ready(db, case=case)
        case.status = "closed"
        case.closed_at = now_utc()

    for field in {"title", "symptom_summary", "suspected_disease"}.intersection(values):
        value = values[field]
        setattr(case, field, _optional_text(value) if field in {"title", "symptom_summary", "suspected_disease"} else value)
    case.updated_at = now_utc()
    db.add(case)
    db.commit()
    db.refresh(case)
    follow_ups = _follow_ups_by_case_id(db, [case.id]).get(case.id, [])
    return _case_response(case, _farm_name(db, case.farm_id), _batch_code(db, case.batch_id), follow_ups)


def delete_current_user_case(db: Session, *, user: User, case_id: UUID) -> None:
    case = _get_owned_case(db, user=user, case_id=case_id)
    if case.status in {"processing", "closed"} or _latest_published_case_review(db, case_id=case.id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已有专家处置或已结案的病例不能删除，历史记录会持续保留")
    _delete_record_assets(db, owner_id=user.id, case_id=case.id)
    db.delete(case)
    db.commit()


def add_current_user_case_follow_up(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    values: dict[str, Any],
) -> CaseResponse:
    case = _get_owned_case(db, user=user, case_id=case_id)
    if case.status == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例已结案，不能新增随访")
    follow_up = HusbandryCaseFollowUp(case_id=case.id, **values)
    case.updated_at = now_utc()
    db.add(follow_up)
    db.add(case)
    db.commit()
    db.refresh(case)
    follow_ups = _follow_ups_by_case_id(db, [case.id]).get(case.id, [])
    return _case_response(case, _farm_name(db, case.farm_id), _batch_code(db, case.batch_id), follow_ups)


def update_current_user_case_follow_up(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    follow_up_id: UUID,
    values: dict[str, Any],
) -> CaseResponse:
    case = _get_owned_case(db, user=user, case_id=case_id)
    if case.status == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例已结案，不能修改随访")
    follow_up = db.scalar(
        select(HusbandryCaseFollowUp).where(
            HusbandryCaseFollowUp.id == follow_up_id,
            HusbandryCaseFollowUp.case_id == case.id,
        )
    )
    if follow_up is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="随访记录不存在")
    for field, value in values.items():
        setattr(follow_up, field, _optional_text(value) if field in {"action_taken", "note"} else value)
    case.updated_at = now_utc()
    db.add(follow_up)
    db.add(case)
    db.commit()
    db.refresh(case)
    follow_ups = _follow_ups_by_case_id(db, [case.id]).get(case.id, [])
    return _case_response(case, _farm_name(db, case.farm_id), _batch_code(db, case.batch_id), follow_ups)


def delete_current_user_case_follow_up(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    follow_up_id: UUID,
) -> None:
    case = _get_owned_case(db, user=user, case_id=case_id)
    if case.status == "closed" or _latest_published_case_review(db, case_id=case.id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="专家复核后的随访记录需要保留，不能删除")
    follow_up = db.scalar(
        select(HusbandryCaseFollowUp).where(
            HusbandryCaseFollowUp.id == follow_up_id,
            HusbandryCaseFollowUp.case_id == case.id,
        )
    )
    if follow_up is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="随访记录不存在")
    case.updated_at = now_utc()
    db.delete(follow_up)
    db.add(case)
    db.commit()


def upload_current_user_daily_record_assets(
    db: Session,
    *,
    user: User,
    batch_id: UUID,
    record_id: UUID,
    attachments: list[HusbandryAttachmentUpload],
) -> list[HusbandryAssetResponse]:
    _get_owned_batch(db, user=user, batch_id=batch_id)
    record = db.scalar(
        select(HusbandryDailyRecord).where(HusbandryDailyRecord.id == record_id, HusbandryDailyRecord.batch_id == batch_id)
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="每日记录不存在")
    return _upload_record_assets(db, user=user, attachments=attachments, daily_record_id=record.id)


def upload_current_user_case_assets(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    attachments: list[HusbandryAttachmentUpload],
) -> list[HusbandryAssetResponse]:
    case = _get_owned_case(db, user=user, case_id=case_id)
    return _upload_record_assets(db, user=user, attachments=attachments, case_id=case.id)


def delete_current_user_record_asset(db: Session, *, user: User, asset_id: UUID) -> None:
    row = db.execute(
        select(HusbandryRecordAsset, UploadedFile)
        .join(UploadedFile, HusbandryRecordAsset.file_id == UploadedFile.id)
        .where(HusbandryRecordAsset.id == asset_id, HusbandryRecordAsset.owner_id == user.id, UploadedFile.deleted_at.is_(None))
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="现场附件不存在")
    asset, uploaded_file = row
    delete_object_file(object_key=uploaded_file.storage_key, failure_detail="附件删除失败，请稍后重试")
    uploaded_file.deleted_at = now_utc()
    db.delete(asset)
    db.add(uploaded_file)
    db.commit()


def get_current_user_husbandry_dashboard(db: Session, *, user: User, farm_id: UUID | None = None) -> HusbandryDashboardResponse:
    if farm_id is not None:
        _get_owned_farm(db, user=user, farm_id=farm_id)
    batch_query = (
        select(SilkwormBatch)
        .join(Farm, SilkwormBatch.farm_id == Farm.id)
        .where(Farm.owner_id == user.id, Farm.status == "active", SilkwormBatch.status == "active")
    )
    if farm_id is not None:
        batch_query = batch_query.where(SilkwormBatch.farm_id == farm_id)
    batches = db.scalars(batch_query).all()
    case_query = select(HusbandryCase).where(HusbandryCase.owner_id == user.id, HusbandryCase.status != "closed")
    if farm_id is not None:
        case_query = case_query.where(HusbandryCase.farm_id == farm_id)
    open_cases = db.scalars(case_query).all()
    follow_up_query = (
        select(HusbandryCaseFollowUp)
        .join(HusbandryCase, HusbandryCaseFollowUp.case_id == HusbandryCase.id)
        .where(
            HusbandryCase.owner_id == user.id,
            HusbandryCase.status != "closed",
            HusbandryCaseFollowUp.next_follow_up_on.is_not(None),
            HusbandryCaseFollowUp.next_follow_up_on <= date.today(),
        )
    )
    if farm_id is not None:
        follow_up_query = follow_up_query.where(HusbandryCase.farm_id == farm_id)
    due_follow_ups = db.scalars(follow_up_query).all()
    daily_query = (
        select(HusbandryDailyRecord)
            .join(SilkwormBatch, HusbandryDailyRecord.batch_id == SilkwormBatch.id)
            .join(Farm, SilkwormBatch.farm_id == Farm.id)
            .where(Farm.owner_id == user.id, HusbandryDailyRecord.record_date == date.today())
    )
    if farm_id is not None:
        daily_query = daily_query.where(SilkwormBatch.farm_id == farm_id)
    today_record_count = len(db.scalars(daily_query).all())
    recent_cases = list_current_user_cases(db, user=user)
    if farm_id is not None:
        recent_cases = [item for item in recent_cases if item.farm_id == str(farm_id)]
    return HusbandryDashboardResponse(
        active_batch_count=len(batches),
        open_case_count=len(open_cases),
        due_follow_up_count=len(due_follow_ups),
        today_record_count=today_record_count,
        recent_cases=recent_cases,
    )


def _get_owned_farm(db: Session, *, user: User, farm_id: UUID) -> Farm:
    farm = db.scalar(select(Farm).where(Farm.id == farm_id, Farm.owner_id == user.id))
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="养殖场不存在")
    return farm


def _get_owned_batch(db: Session, *, user: User, batch_id: UUID) -> SilkwormBatch:
    batch = db.scalar(
        select(SilkwormBatch)
        .join(Farm, SilkwormBatch.farm_id == Farm.id)
        .where(SilkwormBatch.id == batch_id, Farm.owner_id == user.id)
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="养殖批次不存在")
    return batch


def _get_owned_case(db: Session, *, user: User, case_id: UUID) -> HusbandryCase:
    case = db.scalar(select(HusbandryCase).where(HusbandryCase.id == case_id, HusbandryCase.owner_id == user.id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="病例不存在")
    return case


def _get_owned_project(db: Session, *, user: User, project_id: UUID) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id, Project.status != "deleted"))
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


def _get_owned_conversation(db: Session, *, user: User, conversation_id: UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.conversation_type == "diagnosis",
            Conversation.status != "deleted",
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问诊对话不存在")
    return conversation


def _conversation_snapshot(db: Session, *, conversation: Conversation) -> dict[str, Any]:
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc())
    ).all()
    return {
        "conversation_title": conversation.title,
        "summary": conversation.summary,
        "messages": [
            {"role": message.sender_type, "content": message.content[:1200], "created_at": message.created_at.isoformat()}
            for message in messages[-12:]
        ],
    }


def _follow_ups_by_case_id(db: Session, case_ids: list[UUID]) -> dict[UUID, list[CaseFollowUpResponse]]:
    if not case_ids:
        return {}
    rows = db.scalars(
        select(HusbandryCaseFollowUp)
        .where(HusbandryCaseFollowUp.case_id.in_(case_ids))
        .order_by(desc(HusbandryCaseFollowUp.observed_on), desc(HusbandryCaseFollowUp.created_at))
    ).all()
    result: dict[UUID, list[CaseFollowUpResponse]] = defaultdict(list)
    for item in rows:
        result[item.case_id].append(_follow_up_response(item))
    return result


def _farm_response(farm: Farm) -> FarmResponse:
    return FarmResponse(
        id=str(farm.id),
        name=farm.name,
        location=farm.location,
        notes=farm.notes,
        status=farm.status,
        created_at=farm.created_at,
        updated_at=farm.updated_at,
    )


def _batch_response(batch: SilkwormBatch, farm_name: str) -> BatchResponse:
    return BatchResponse(
        id=str(batch.id),
        farm_id=str(batch.farm_id),
        project_id=str(batch.project_id) if batch.project_id else None,
        farm_name=farm_name,
        batch_code=batch.batch_code,
        variety=batch.variety,
        instar=batch.instar,
        start_date=batch.start_date,
        expected_cocooning_date=batch.expected_cocooning_date,
        population_count=batch.population_count,
        notes=batch.notes,
        status=batch.status,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
    )


def _daily_record_response(
    record: HusbandryDailyRecord,
    assets: list[HusbandryAssetResponse] | None = None,
) -> DailyRecordResponse:
    return DailyRecordResponse(
        id=str(record.id),
        batch_id=str(record.batch_id),
        record_date=record.record_date,
        temperature_celsius=record.temperature_celsius,
        humidity_percent=record.humidity_percent,
        feedings=record.feedings,
        leaf_amount_kg=record.leaf_amount_kg,
        sick_count=record.sick_count,
        death_count=record.death_count,
        observations=record.observations,
        management_notes=record.management_notes,
        created_at=record.created_at,
        updated_at=record.updated_at,
        assets=assets or [],
    )


def _case_response(
    case: HusbandryCase,
    farm_name: str,
    batch_code: str | None,
    follow_ups: list[CaseFollowUpResponse],
    expert_reviews: list[HusbandryExpertReviewResponse] | None = None,
    assets: list[HusbandryAssetResponse] | None = None,
) -> CaseResponse:
    return CaseResponse(
        id=str(case.id),
        farm_id=str(case.farm_id),
        batch_id=str(case.batch_id) if case.batch_id else None,
        project_id=str(case.project_id) if case.project_id else None,
        source_conversation_id=str(case.source_conversation_id) if case.source_conversation_id else None,
        farm_name=farm_name,
        batch_code=batch_code,
        title=case.title,
        occurred_on=case.occurred_on,
        symptom_summary=case.symptom_summary,
        suspected_disease=case.suspected_disease,
        severity=case.severity,
        status=case.status,
        diagnosis_summary=case.diagnosis_summary,
        recommendation=case.recommendation,
        source_snapshot=case.source_snapshot or {},
        created_at=case.created_at,
        updated_at=case.updated_at,
        closed_at=case.closed_at,
        follow_ups=follow_ups,
        assets=assets or [],
        expert_reviews=expert_reviews or [],
    )


def _published_expert_reviews_by_case_id(
    db: Session,
    case_ids: list[UUID],
) -> dict[UUID, list[HusbandryExpertReviewResponse]]:
    """Read administrator-owned reviews without coupling the user service to admin deployment order."""
    if not case_ids:
        return {}
    try:
        rows = db.execute(
            text(
                """
                SELECT husbandry_case_id::text AS case_id, id::text AS id, reviewer_name_snapshot,
                       risk_level, conclusion, recommendation, evidence, version, published_at
                  FROM admin.expert_reviews
                 WHERE husbandry_case_id = ANY(CAST(:case_ids AS uuid[]))
                   AND status = 'published'
                 ORDER BY husbandry_case_id, version DESC
                """
            ),
            {"case_ids": [str(case_id) for case_id in case_ids]},
        ).mappings().all()
    except SQLAlchemyError:
        db.rollback()
        return {}

    result: dict[UUID, list[HusbandryExpertReviewResponse]] = defaultdict(list)
    for row in rows:
        if row["published_at"] is None or row["risk_level"] not in {"low", "medium", "high", "critical"}:
            continue
        result[UUID(row["case_id"])].append(
            HusbandryExpertReviewResponse(
                id=row["id"],
                reviewer_name=row["reviewer_name_snapshot"],
                risk_level=row["risk_level"],
                conclusion=row["conclusion"],
                recommendation=row["recommendation"],
                evidence=row["evidence"] or [],
                version=int(row["version"]),
                published_at=row["published_at"],
            )
        )
    return result


def _latest_published_case_review(db: Session, *, case_id: UUID) -> dict[str, Any] | None:
    """Read the lifecycle gate from the admin-owned review ledger.

    A user must never be able to close a case merely because the UI hides the
    action. The check lives here so direct API calls follow the same rule.
    """
    try:
        row = db.execute(
            text(
                """
                SELECT id::text AS id, published_at
                  FROM admin.expert_reviews
                 WHERE husbandry_case_id = CAST(:case_id AS uuid)
                   AND status = 'published'
                 ORDER BY version DESC
                 LIMIT 1
                """
            ),
            {"case_id": str(case_id)},
        ).mappings().first()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="专家复核状态暂不可用，请稍后再试") from error
    return dict(row) if row else None


def _require_user_case_closure_ready(db: Session, *, case: HusbandryCase) -> None:
    if case.status != "processing":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例需先由专家发布复核意见并进入处理中，才能结案")
    review = _latest_published_case_review(db, case_id=case.id)
    if review is None or review.get("published_at") is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚无已发布的专家复核意见，不能结案")
    has_follow_up = db.scalar(
        select(HusbandryCaseFollowUp.id).where(
            HusbandryCaseFollowUp.case_id == case.id,
            HusbandryCaseFollowUp.created_at >= review["published_at"],
        ).limit(1)
    )
    if has_follow_up is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先记录发布专家意见后的处置随访，再完成结案")


def _follow_up_response(follow_up: HusbandryCaseFollowUp) -> CaseFollowUpResponse:
    return CaseFollowUpResponse(
        id=str(follow_up.id),
        case_id=str(follow_up.case_id),
        observed_on=follow_up.observed_on,
        action_taken=follow_up.action_taken,
        note=follow_up.note,
        affected_count=follow_up.affected_count,
        death_count=follow_up.death_count,
        next_follow_up_on=follow_up.next_follow_up_on,
        created_at=follow_up.created_at,
    )


def _assets_by_owner_ids(
    db: Session,
    *,
    daily_record_ids: list[UUID] | None = None,
    case_ids: list[UUID] | None = None,
) -> dict[str, dict[UUID, list[HusbandryAssetResponse]]]:
    daily_record_ids = daily_record_ids or []
    case_ids = case_ids or []
    result: dict[str, dict[UUID, list[HusbandryAssetResponse]]] = {
        "daily": defaultdict(list),
        "case": defaultdict(list),
    }
    predicates = []
    if daily_record_ids:
        predicates.append(HusbandryRecordAsset.daily_record_id.in_(daily_record_ids))
    if case_ids:
        predicates.append(HusbandryRecordAsset.case_id.in_(case_ids))
    if not predicates:
        return result
    rows = db.execute(
        select(HusbandryRecordAsset, UploadedFile)
        .join(UploadedFile, HusbandryRecordAsset.file_id == UploadedFile.id)
        .where(or_(*predicates), UploadedFile.deleted_at.is_(None))
        .order_by(HusbandryRecordAsset.created_at.asc())
    ).all()
    for asset, uploaded_file in rows:
        if asset.daily_record_id is not None:
            result["daily"][asset.daily_record_id].append(_asset_response(asset, uploaded_file))
        elif asset.case_id is not None:
            result["case"][asset.case_id].append(_asset_response(asset, uploaded_file))
    return result


def _asset_response(asset: HusbandryRecordAsset, uploaded_file: UploadedFile) -> HusbandryAssetResponse:
    return HusbandryAssetResponse(
        id=str(asset.id),
        file_id=str(uploaded_file.id),
        file_name=uploaded_file.file_name,
        file_type=uploaded_file.file_type,
        mime_type=uploaded_file.mime_type,
        storage_url=uploaded_file.storage_url,
        file_size=uploaded_file.file_size,
        created_at=asset.created_at,
    )


def _upload_record_assets(
    db: Session,
    *,
    user: User,
    attachments: list[HusbandryAttachmentUpload],
    daily_record_id: UUID | None = None,
    case_id: UUID | None = None,
) -> list[HusbandryAssetResponse]:
    uploaded_assets: list[tuple[HusbandryRecordAsset, UploadedFile]] = []
    for index, attachment in enumerate(attachments, start=1):
        if not attachment.content:
            continue
        normalized_content_type = _normalize_husbandry_media_type(attachment.file_name, attachment.content_type)
        file_type = "image" if normalized_content_type.startswith("image/") else "video"
        file_id = uuid.uuid4()
        safe_file_name = _safe_husbandry_file_name(attachment.file_name or f"field-asset-{index}")
        object_key = f"husbandry/{user.id}/{daily_record_id or case_id}/{file_id}/original/{safe_file_name}"
        storage_url = upload_object_file(
            object_key=object_key,
            content=attachment.content,
            content_type=normalized_content_type,
            failure_detail="现场附件上传失败，请稍后重试",
        )
        uploaded_file = UploadedFile(
            id=file_id,
            user_id=user.id,
            file_name=attachment.file_name or safe_file_name,
            file_type=file_type,
            mime_type=normalized_content_type,
            storage_key=object_key,
            storage_url=storage_url,
            file_size=len(attachment.content),
            checksum=hashlib.sha256(attachment.content).hexdigest(),
            metadata_={"source": "husbandry_asset", "upload_state": "ready"},
        )
        asset = HusbandryRecordAsset(
            owner_id=user.id,
            daily_record_id=daily_record_id,
            case_id=case_id,
            file_id=file_id,
        )
        db.add(uploaded_file)
        db.add(asset)
        uploaded_assets.append((asset, uploaded_file))
    db.commit()
    for asset, _ in uploaded_assets:
        db.refresh(asset)
    return [_asset_response(asset, uploaded_file) for asset, uploaded_file in uploaded_assets]


def _delete_record_assets(
    db: Session,
    *,
    owner_id: UUID,
    daily_record_id: UUID | None = None,
    case_id: UUID | None = None,
) -> None:
    predicate = HusbandryRecordAsset.daily_record_id == daily_record_id if daily_record_id is not None else HusbandryRecordAsset.case_id == case_id
    rows = db.execute(
        select(HusbandryRecordAsset, UploadedFile)
        .join(UploadedFile, HusbandryRecordAsset.file_id == UploadedFile.id)
        .where(HusbandryRecordAsset.owner_id == owner_id, predicate, UploadedFile.deleted_at.is_(None))
    ).all()
    for asset, uploaded_file in rows:
        try:
            delete_object_file(object_key=uploaded_file.storage_key, failure_detail="附件删除失败，请稍后重试")
        except HTTPException:
            # The relational delete must still succeed; the file remains soft-deleted and can be cleaned asynchronously.
            pass
        uploaded_file.deleted_at = now_utc()
        db.delete(asset)
        db.add(uploaded_file)


def _normalize_husbandry_media_type(file_name: str, content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if not normalized or normalized == "application/octet-stream":
        normalized = mimetypes.guess_type(file_name)[0] or ""
    if not (normalized.startswith("image/") or normalized.startswith("video/")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="现场附件仅支持图片或视频")
    return normalized


def _safe_husbandry_file_name(file_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name.strip())
    normalized = normalized.strip(".-")
    return normalized[:160] or "field-asset"


def _farm_name(db: Session, farm_id: UUID) -> str:
    return db.scalar(select(Farm.name).where(Farm.id == farm_id)) or "已删除养殖场"


def _batch_code(db: Session, batch_id: UUID | None) -> str | None:
    if batch_id is None:
        return None
    return db.scalar(select(SilkwormBatch.batch_code).where(SilkwormBatch.id == batch_id))


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
