from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import datetime
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from models import User, AccountLedger, LedgerType
from services.ledger_service import (
    record_debit, record_credit, calculate_balance, get_ledger_entries,
    get_ledger_entries_by_reference
)
from .auth import get_current_active_user


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Pydantic模型
class LedgerEntryResponse(BaseModel):
    id: int
    entity_id: int
    type: LedgerType
    amount: float
    description: str
    reference_id: Optional[int]
    reference_type: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LedgerRecord(BaseModel):
    type: LedgerType
    amount: float
    description: str
    reference_id: Optional[int] = None
    reference_type: Optional[str] = None


class BalanceResponse(BaseModel):
    entity_id: int
    balance: float
    timestamp: datetime


@router.post("/api/ledger/record", response_model=LedgerEntryResponse)
async def record_transaction(
    ledger_record: LedgerRecord,
    current_user: User = Depends(get_current_active_user)
):
    """记录交易"""
    if ledger_record.amount <= 0:
        raise HTTPException(status_code=400, detail="金额必须大于0")
    
    if ledger_record.type == LedgerType.DEBIT:
        entry = await record_debit(
            entity_id=current_user.id,
            amount=ledger_record.amount,
            description=ledger_record.description,
            reference_id=ledger_record.reference_id,
            reference_type=ledger_record.reference_type
        )
    else:
        entry = await record_credit(
            entity_id=current_user.id,
            amount=ledger_record.amount,
            description=ledger_record.description,
            reference_id=ledger_record.reference_id,
            reference_type=ledger_record.reference_type
        )
    
    return entry


@router.get("/api/ledger/entries", response_model=List[LedgerEntryResponse])
async def get_ledger_entries_route(
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user)
):
    """获取当前用户的记账条目"""
    entries = await get_ledger_entries(
        entity_id=current_user.id,
        limit=limit,
        offset=offset
    )
    return entries


@router.get("/api/ledger/balance", response_model=BalanceResponse)
async def get_balance(
    current_user: User = Depends(get_current_active_user)
):
    """获取当前用户的账户余额"""
    balance = await calculate_balance(entity_id=current_user.id)
    return {
        "entity_id": current_user.id,
        "balance": balance,
        "timestamp": datetime.now()
    }


@router.get("/api/ledger/entries/{reference_id}/{reference_type}", response_model=List[LedgerEntryResponse])
async def get_entries_by_reference(
    reference_id: int,
    reference_type: str,
    limit: int = 100,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user)
):
    """根据关联ID和类型获取记账条目"""
    entries = await get_ledger_entries_by_reference(
        reference_id=reference_id,
        reference_type=reference_type,
        limit=limit,
        offset=offset
    )
    return entries


@router.get("/api/ledger/reports/balance")
async def get_balance_report(
    user_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user)
):
    """获取余额报表"""
    # 只有管理员可以查询其他用户的余额
    if user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以查询其他用户的余额")
    
    target_user_id = user_id or current_user.id
    balance = await calculate_balance(entity_id=target_user_id)
    return {
        "user_id": target_user_id,
        "balance": balance,
        "timestamp": datetime.now()
    }