from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from models import (
    User, Invoice, InvoiceStatus, Order, UserRole, LoanApplication, LoanApplicationStatus
)
from services.ledger_service import record_debit, record_credit
from datetime import datetime
from .auth import get_current_active_user, get_current_supplier_user, get_current_buyer_user


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Pydantic模型
class InvoiceResponse(BaseModel):
    id: int
    order_id: int
    due_date: datetime
    amount: float
    status: InvoiceStatus
    invoice_number: str
    remaining_amount: float
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InvoiceUpdate(BaseModel):
    status: Optional[InvoiceStatus] = None


@router.get("/api/invoices", response_model=List[InvoiceResponse])
async def get_invoices(
    status: Optional[InvoiceStatus] = None,
    current_user: User = Depends(get_current_active_user)
):
    """获取发票列表"""
    if current_user.role == UserRole.SUPPLIER:
        # 供应商只能看到自己作为供应商的订单的发票
        orders = await Order.filter(supplier_id=current_user.id).values_list("id", flat=True)
        query = Invoice.filter(order_id__in=orders)
    elif current_user.role == UserRole.BUYER:
        # 购买方只能看到自己作为购买方的订单的发票
        orders = await Order.filter(buyer_id=current_user.id).values_list("id", flat=True)
        query = Invoice.filter(order_id__in=orders)
    else:
        # 管理员和贷款方可以看到所有发票
        query = Invoice.all()
    
    if status:
        query = query.filter(status=status)
    
    invoices = await query.order_by("-created_at").all()
    return invoices


@router.get("/api/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """获取单个发票"""
    invoice = await Invoice.get_or_none(id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="发票不存在")
    
    # 获取关联订单
    order = await invoice.order
    
    # 检查权限
    if current_user.role == UserRole.SUPPLIER and order.supplier_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该发票")
    if current_user.role == UserRole.BUYER and order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该发票")
    
    return invoice


@router.put("/api/invoices/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    invoice_update: InvoiceUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """更新发票"""
    invoice = await Invoice.get_or_none(id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="发票不存在")
    
    order = await invoice.order
    
    # 检查权限
    if current_user.role == UserRole.BUYER and order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权更新该发票")
    
    # 更新发票状态
    if invoice_update.status:
        # 如果发票状态变为已支付，处理相关逻辑
        if invoice_update.status == InvoiceStatus.PAID:
            # 检查是否有未处理的贷款申请
            pending_applications = await LoanApplication.filter(
                invoice_id=invoice.id,
                status=LoanApplicationStatus.PENDING
            ).count()
            if pending_applications > 0:
                raise HTTPException(
                    status_code=400,
                    detail="该发票有未处理的贷款申请，无法支付"
                )
            
            # 更新发票剩余金额
            invoice.remaining_amount = 0.0
            invoice.status = InvoiceStatus.PAID
            
            # 更新关联订单状态为已支付
            order.status = OrderStatus.PAID
            await order.save()
            
            # 记录记账
            # 供应商账户增加收入
            await record_credit(
                entity_id=order.supplier_id,
                amount=invoice.amount,
                description=f"发票支付: {invoice.invoice_number}",
                reference_id=invoice.id,
                reference_type="invoice"
            )
            
            # 购买方账户减少支出
            await record_debit(
                entity_id=order.buyer_id,
                amount=invoice.amount,
                description=f"支付发票: {invoice.invoice_number}",
                reference_id=invoice.id,
                reference_type="invoice"
            )
        else:
            invoice.status = invoice_update.status
    
    await invoice.save()
    return invoice


@router.post("/api/invoices/{invoice_id}/pay/mock")
async def mock_pay_invoice(
    invoice_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """模拟支付发票"""
    invoice = await Invoice.get_or_none(id=invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="发票不存在")
    
    order = await invoice.order
    
    # 检查是否已经支付
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="发票已支付")
    
    # 更新发票状态为已支付
    invoice.status = InvoiceStatus.PAID
    invoice.remaining_amount = 0.0
    await invoice.save()
    
    # 更新订单状态为已支付
    order.status = OrderStatus.PAID
    await order.save()
    
    # 记录记账
    await record_credit(
        entity_id=order.supplier_id,
        amount=invoice.amount,
        description=f"发票支付: {invoice.invoice_number} (模拟)",
        reference_id=invoice.id,
        reference_type="invoice"
    )
    
    await record_debit(
        entity_id=order.buyer_id,
        amount=invoice.amount,
        description=f"支付发票: {invoice.invoice_number} (模拟)",
        reference_id=invoice.id,
        reference_type="invoice"
    )
    
    return {"message": "发票支付成功 (模拟)", "invoice_id": invoice.id, "status": "paid"}