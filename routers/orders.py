from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from models import User, Order, OrderStatus, UserRole, Invoice, InvoiceStatus
from services.ledger_service import record_debit, record_credit
from datetime import datetime, timedelta
from .auth import get_current_active_user, get_current_supplier_user, get_current_buyer_user


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Pydantic模型
class OrderCreate(BaseModel):
    buyer_id: int
    amount: float
    description: Optional[str] = None
    po_number: Optional[str] = None


class OrderUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    description: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    supplier_id: int
    buyer_id: int
    amount: float
    status: OrderStatus
    description: Optional[str]
    po_number: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/api/orders", response_model=OrderResponse)
async def create_order(
    order_create: OrderCreate,
    current_user: User = Depends(get_current_supplier_user)
):
    """创建订单 (供应商)"""
    # 检查购买方是否存在
    buyer = await User.get_or_none(id=order_create.buyer_id, role=UserRole.BUYER)
    if not buyer:
        raise HTTPException(status_code=404, detail="购买方不存在")
    
    # 创建订单
    order = await Order.create(
        supplier_id=current_user.id,
        buyer_id=buyer.id,
        amount=order_create.amount,
        description=order_create.description,
        po_number=order_create.po_number
    )
    
    return order


@router.get("/api/orders", response_model=List[OrderResponse])
async def get_orders(
    status: Optional[OrderStatus] = None,
    current_user: User = Depends(get_current_active_user)
):
    """获取订单列表 (根据角色返回不同订单)"""
    if current_user.role == UserRole.SUPPLIER:
        # 供应商只能看到自己作为供应商的订单
        query = Order.filter(supplier_id=current_user.id)
    elif current_user.role == UserRole.BUYER:
        # 购买方只能看到自己作为购买方的订单
        query = Order.filter(buyer_id=current_user.id)
    else:
        # 管理员和贷款方可以看到所有订单
        query = Order.all()
    
    if status:
        query = query.filter(status=status)
    
    orders = await query.order_by("-created_at").all()
    return orders


@router.get("/api/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """获取单个订单"""
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    
    # 检查权限
    if current_user.role == UserRole.SUPPLIER and order.supplier_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该订单")
    if current_user.role == UserRole.BUYER and order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该订单")
    
    return order


@router.put("/api/orders/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    order_update: OrderUpdate,
    current_user: User = Depends(get_current_active_user)
):
    """更新订单"""
    order = await Order.get_or_none(id=order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    
    # 检查权限
    if current_user.role == UserRole.SUPPLIER and order.supplier_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权更新该订单")
    if current_user.role == UserRole.BUYER and order.buyer_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权更新该订单")
    
    # 更新订单状态
    if order_update.status:
        order.status = order_update.status
        
        # 如果订单状态变为已确认，自动生成发票
        if order_update.status == OrderStatus.CONFIRMED:
            # 生成唯一发票号
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{order.id}"
            
            # 发票到期日期为订单确认后30天
            due_date = datetime.now() + timedelta(days=30)
            
            # 创建发票
            await Invoice.create(
                order_id=order.id,
                due_date=due_date,
                amount=order.amount,
                status=InvoiceStatus.UNPAID,
                invoice_number=invoice_number,
                remaining_amount=order.amount
            )
    
    # 更新描述
    if order_update.description:
        order.description = order_update.description
    
    await order.save()
    return order


@router.delete("/api/orders/{order_id}")
async def delete_order(
    order_id: int,
    current_user: User = Depends(get_current_supplier_user)
):
    """删除订单 (供应商)"""
    order = await Order.get_or_none(id=order_id, supplier_id=current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在或无权删除")
    
    # 只有待确认的订单可以删除
    if order.status != OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="只有待确认的订单可以删除")
    
    await order.delete()
    return {"message": "订单删除成功"}