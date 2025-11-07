from fastapi import APIRouter, Depends, HTTPException, status, Request
from datetime import datetime
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from models import User, UserRole, Order, Invoice, Loan, LoanApplication
from services.auth_service import get_password_hash
from .auth import get_current_admin_user


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Pydantic模型
class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[UserRole] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    id: int
    username: str
    role: UserRole
    email: Optional[str]
    phone: Optional[str]
    company_name: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SystemStats(BaseModel):
    total_users: int
    total_suppliers: int
    total_buyers: int
    total_lenders: int
    total_orders: int
    total_invoices: int
    total_loans: int
    total_pending_loan_applications: int


@router.get("/api/admin/users", response_model=List[UserResponse])
async def get_all_users(
    current_user: User = Depends(get_current_admin_user)
):
    """获取所有用户 (管理员)"""
    users = await User.all().order_by("-created_at")
    return users


@router.post("/api/admin/users", response_model=UserResponse)
async def create_user(
    user_create: UserCreate,
    current_user: User = Depends(get_current_admin_user)
):
    """创建用户 (管理员)"""
    # 检查用户名是否已存在
    existing_user = await User.get_or_none(username=user_create.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    # 创建用户
    hashed_password = get_password_hash(user_create.password)
    user = await User.create(
        username=user_create.username,
        hashed_password=hashed_password,
        role=user_create.role,
        email=user_create.email,
        phone=user_create.phone,
        company_name=user_create.company_name,
        is_active=user_create.is_active
    )
    
    return user


@router.get("/api/admin/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user)
):
    """获取单个用户 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return user


@router.put("/api/admin/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(get_current_admin_user)
):
    """更新用户 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 更新密码
    if user_update.password:
        user.hashed_password = get_password_hash(user_update.password)
    
    # 更新角色
    if user_update.role:
        user.role = user_update.role
    
    # 更新邮箱
    if user_update.email:
        user.email = user_update.email
    
    # 更新电话
    if user_update.phone:
        user.phone = user_update.phone
    
    # 更新公司名称
    if user_update.company_name:
        user.company_name = user_update.company_name
    
    # 更新激活状态
    if user_update.is_active is not None:
        user.is_active = user_update.is_active
    
    await user.save()
    return user


@router.delete("/api/admin/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user)
):
    """删除用户 (管理员)"""
    user = await User.get_or_none(id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    await user.delete()
    return {"message": "用户删除成功"}


@router.get("/api/admin/stats", response_model=SystemStats)
async def get_system_stats(
    current_user: User = Depends(get_current_admin_user)
):
    """获取系统统计数据 (管理员)"""
    total_users = await User.count()
    total_suppliers = await User.filter(role=UserRole.SUPPLIER).count()
    total_buyers = await User.filter(role=UserRole.BUYER).count()
    total_lenders = await User.filter(role=UserRole.LENDER).count()
    total_orders = await Order.count()
    total_invoices = await Invoice.count()
    total_loans = await Loan.count()
    total_pending_loan_applications = await LoanApplication.filter(
        status="pending"
    ).count()
    
    return SystemStats(
        total_users=total_users,
        total_suppliers=total_suppliers,
        total_buyers=total_buyers,
        total_lenders=total_lenders,
        total_orders=total_orders,
        total_invoices=total_invoices,
        total_loans=total_loans,
        total_pending_loan_applications=total_pending_loan_applications
    )


@router.get("/api/admin/reports/loan-risk")
async def get_loan_risk_report(
    current_user: User = Depends(get_current_admin_user)
):
    """获取贷款风险报告 (管理员)"""
    # 获取所有贷款申请
    applications = await LoanApplication.all().prefetch_related("invoice", "applicant")
    
    # 按风险评分分类
    low_risk = []  # 70-100
    medium_risk = []  # 40-69
    high_risk = []  # 0-39
    
    for app in applications:
        risk_score = app.risk_score or 0
        if risk_score >= 70:
            low_risk.append(app)
        elif risk_score >= 40:
            medium_risk.append(app)
        else:
            high_risk.append(app)
    
    return {
        "low_risk": len(low_risk),
        "medium_risk": len(medium_risk),
        "high_risk": len(high_risk),
        "total": len(applications)
    }