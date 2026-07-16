from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.husbandry import (
    BatchCreateRequest,
    BatchUpdateRequest,
    BatchResponse,
    CaseCreateRequest,
    CaseFollowUpCreateRequest,
    CaseFollowUpUpdateRequest,
    CaseResponse,
    CaseUpdateRequest,
    DailyRecordResponse,
    DailyRecordUpsertRequest,
    FarmCreateRequest,
    FarmUpdateRequest,
    FarmResponse,
    HusbandryDashboardResponse,
    HusbandryAssetResponse,
)
from app.services.auth_service import get_current_user
from app.services.husbandry_service import (
    add_current_user_case_follow_up,
    create_current_user_batch,
    create_current_user_case,
    create_current_user_farm,
    delete_current_user_case,
    delete_current_user_case_follow_up,
    delete_current_user_daily_record,
    delete_current_user_record_asset,
    get_current_user_husbandry_dashboard,
    list_current_user_batches,
    list_current_user_cases,
    list_current_user_daily_records,
    list_current_user_farms,
    update_current_user_case,
    update_current_user_case_follow_up,
    update_current_user_farm,
    update_current_user_batch,
    upsert_current_user_daily_record,
    upload_current_user_case_assets,
    upload_current_user_daily_record_assets,
    HusbandryAttachmentUpload,
)


router = APIRouter(prefix="/husbandry", tags=["husbandry"])


@router.get("/dashboard", response_model=HusbandryDashboardResponse)
def get_husbandry_dashboard(request: Request, farm_id: UUID | None = None, db: Session = Depends(get_db_session)) -> HusbandryDashboardResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_current_user_husbandry_dashboard(db, user=user, farm_id=farm_id)


@router.get("/farms", response_model=list[FarmResponse])
def list_farms(request: Request, include_archived: bool = False, db: Session = Depends(get_db_session)) -> list[FarmResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_farms(db, user=user, include_archived=include_archived)


@router.post("/farms", response_model=FarmResponse, status_code=status.HTTP_201_CREATED)
def create_farm(
    payload: FarmCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> FarmResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_farm(db, user=user, name=payload.name, location=payload.location, notes=payload.notes)


@router.patch("/farms/{farm_id}", response_model=FarmResponse)
def update_farm(farm_id: UUID, payload: FarmUpdateRequest, request: Request, db: Session = Depends(get_db_session)) -> FarmResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_farm(db, user=user, farm_id=farm_id, values=payload.model_dump(exclude_unset=True))


@router.get("/batches", response_model=list[BatchResponse])
def list_batches(
    request: Request,
    farm_id: UUID | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db_session),
) -> list[BatchResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_batches(db, user=user, farm_id=farm_id, include_archived=include_archived)


@router.post("/batches", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
def create_batch(
    payload: BatchCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> BatchResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_batch(db, user=user, **payload.model_dump())


@router.patch("/batches/{batch_id}", response_model=BatchResponse)
def update_batch(batch_id: UUID, payload: BatchUpdateRequest, request: Request, db: Session = Depends(get_db_session)) -> BatchResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_batch(db, user=user, batch_id=batch_id, values=payload.model_dump(exclude_unset=True))


@router.get("/batches/{batch_id}/daily-records", response_model=list[DailyRecordResponse])
def list_daily_records(
    batch_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[DailyRecordResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_daily_records(db, user=user, batch_id=batch_id)


@router.put("/batches/{batch_id}/daily-records", response_model=DailyRecordResponse)
def upsert_daily_record(
    batch_id: UUID,
    payload: DailyRecordUpsertRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DailyRecordResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return upsert_current_user_daily_record(db, user=user, batch_id=batch_id, values=payload.model_dump())


@router.post("/batches/{batch_id}/daily-records/{record_id}/assets", response_model=list[HusbandryAssetResponse], status_code=status.HTTP_201_CREATED)
async def upload_daily_record_assets(
    batch_id: UUID,
    record_id: UUID,
    request: Request,
    attachments: list[UploadFile] = File(...),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[HusbandryAssetResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    prepared = await _prepare_husbandry_attachments(attachments, settings=settings)
    return upload_current_user_daily_record_assets(db, user=user, batch_id=batch_id, record_id=record_id, attachments=prepared)


@router.delete("/batches/{batch_id}/daily-records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_daily_record(batch_id: UUID, record_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> None:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_daily_record(db, user=user, batch_id=batch_id, record_id=record_id)


@router.get("/cases", response_model=list[CaseResponse])
def list_cases(
    request: Request,
    batch_id: UUID | None = None,
    case_status: str | None = None,
    db: Session = Depends(get_db_session),
) -> list[CaseResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_cases(db, user=user, batch_id=batch_id, case_status=case_status)


@router.post("/cases", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    payload: CaseCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CaseResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_case(db, user=user, values=payload.model_dump())


@router.patch("/cases/{case_id}", response_model=CaseResponse)
def update_case(
    case_id: UUID,
    payload: CaseUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CaseResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_case(db, user=user, case_id=case_id, values=payload.model_dump(exclude_unset=True))


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> None:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_case(db, user=user, case_id=case_id)


@router.post("/cases/{case_id}/follow-ups", response_model=CaseResponse)
def add_case_follow_up(
    case_id: UUID,
    payload: CaseFollowUpCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CaseResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return add_current_user_case_follow_up(db, user=user, case_id=case_id, values=payload.model_dump())


@router.patch("/cases/{case_id}/follow-ups/{follow_up_id}", response_model=CaseResponse)
def update_case_follow_up(
    case_id: UUID,
    follow_up_id: UUID,
    payload: CaseFollowUpUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CaseResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_case_follow_up(
        db,
        user=user,
        case_id=case_id,
        follow_up_id=follow_up_id,
        values=payload.model_dump(exclude_unset=True),
    )


@router.delete("/cases/{case_id}/follow-ups/{follow_up_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_follow_up(case_id: UUID, follow_up_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_case_follow_up(db, user=user, case_id=case_id, follow_up_id=follow_up_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/cases/{case_id}/assets", response_model=list[HusbandryAssetResponse], status_code=status.HTTP_201_CREATED)
async def upload_case_assets(
    case_id: UUID,
    request: Request,
    attachments: list[UploadFile] = File(...),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[HusbandryAssetResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    prepared = await _prepare_husbandry_attachments(attachments, settings=settings)
    return upload_current_user_case_assets(db, user=user, case_id=case_id, attachments=prepared)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record_asset(asset_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_record_asset(db, user=user, asset_id=asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _prepare_husbandry_attachments(
    attachments: list[UploadFile],
    *,
    settings: Settings,
) -> list[HusbandryAttachmentUpload]:
    if not attachments:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请至少选择一张图片或一个视频")
    if len(attachments) > settings.multimodal_attachment_max_count:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"一次最多上传 {settings.multimodal_attachment_max_count} 个现场附件")
    prepared: list[HusbandryAttachmentUpload] = []
    for attachment in attachments:
        content = await attachment.read(settings.multimodal_attachment_max_bytes + 1)
        if len(content) > settings.multimodal_attachment_max_bytes:
            max_mb = max(1, settings.multimodal_attachment_max_bytes // 1024 // 1024)
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"单个现场附件不能超过 {max_mb}MB")
        prepared.append(
            HusbandryAttachmentUpload(
                file_name=attachment.filename or "field-asset",
                content_type=attachment.content_type or "application/octet-stream",
                content=content,
            )
        )
    return prepared


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return token.strip()
