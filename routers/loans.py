from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List
from models import (
    User, LoanApplication, LoanApplicationStatus, Invoice, Loan, LoanStatus, UserRole
)
from services.loan_service import calculate_risk_score, check_loan_eligibility
from services.ledger_service import record_debit, record_credit
from datetime import datetime, timedelta
from .auth import (
    get_current_active_user, get_current_supplier_user, get_current_buyer_user,
    get_current_lender_user
)


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Pydantic模型
class LoanApplicationCreate(BaseModel):
    invoice_id: int
    amount_requested: float
    reason: Optional[str] = None


class LoanApplicationResponse(BaseModel):
    id: int
    applicant_id: int
    invoice_id: int
    amount_requested: float
    status: LoanApplicationStatus
    reason: Optional[str]
    risk_score: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LoanApplicationUpdate(BaseModel):
    status: LoanApplicationStatus
    risk_score: Optional[float] = None


class LoanCreate(BaseModel):
    application_id: int
    interest_rate: float
    repayment_date: datetime


class LoanResponse(BaseModel):
    id: int
    application_id: int
    lender_id: int
    interest_rate: float
    repayment_date: datetime
    amount: float
    status: LoanStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/api/loans/apply", response_model=LoanApplicationResponse)
async def apply_for_loan(
    loan_application: LoanApplicationCreate,
    current_user: User = Depends(get_current_active_user)
):
    """提交贷款申请 (供应商或购买方)"""
    # 检查用户角色是否符合要求
    if current_user.role not in [UserRole.SUPPLIER, UserRole.BUYER]:
        raise HTTPException(status_code=403, detail="只有供应商和购买方可以申请贷款")
    
    # 检查贷款资格
    eligible, message = await check_loan_eligibility(
        loan_application.invoice_id,
        loan_application.amount_requested
    )
    if not eligible:
        raise HTTPException(status_code=400, detail=message)
    
    # 创建贷款申请
    application = await LoanApplication.create(
        applicant_id=current_user.id,
        invoice_id=loan_application.invoice_id,
        amount_requested=loan_application.amount_requested,
        reason=loan_application.reason
    )
    
    # 计算风险评分
    application.risk_score = await calculate_risk_score(application)
    await application.save()
    
    return application


@router.get("/api/loans/applications", response_model=List[LoanApplicationResponse])
async def get_loan_applications(
    status: Optional[LoanApplicationStatus] = None,
    current_user: User = Depends(get_current_active_user)
):
    """获取贷款申请列表"""
    if current_user.role == UserRole.SUPPLIER or current_user.role == UserRole.BUYER:
        # 供应商和购买方只能看到自己的申请
        query = LoanApplication.filter(applicant_id=current_user.id)
    elif current_user.role == UserRole.LENDER:
        # 贷款方可以看到所有待审核的申请
        query = LoanApplication.filter(status=LoanApplicationStatus.PENDING)
    else:
        # 管理员可以看到所有申请
        query = LoanApplication.all()
    
    if status:
        query = query.filter(status=status)
    
    applications = await query.order_by("-created_at").all()
    return applications


@router.get("/api/loans/applications/{application_id}", response_model=LoanApplicationResponse)
async def get_loan_application(
    application_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """获取单个贷款申请"""
    application = await LoanApplication.get_or_none(id=application_id)
    if not application:
        raise HTTPException(status_code=404, detail="贷款申请不存在")
    
    # 检查权限
    if current_user.role == UserRole.SUPPLIER or current_user.role == UserRole.BUYER:
        if application.applicant_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该贷款申请")
    
    return application


@router.put("/api/loans/applications/{application_id}", response_model=LoanApplicationResponse)
async def update_loan_application(
    application_id: int,
    application_update: LoanApplicationUpdate,
    current_user: User = Depends(get_current_lender_user)
):
    """更新贷款申请状态 (贷款方)"""
    application = await LoanApplication.get_or_none(id=application_id)
    if not application:
        raise HTTPException(status_code=404, detail="贷款申请不存在")
    
    # 只有待审核的申请可以被处理
    if application.status != LoanApplicationStatus.PENDING:
        raise HTTPException(status_code=400, detail="该贷款申请已处理")
    
    # 更新申请状态
    application.status = application_update.status
    
    # 如果有风险评分，更新风险评分
    if application_update.risk_score:
        application.risk_score = application_update.risk_score
    
    await application.save()
    
    # 如果申请被批准，创建贷款
    if application.status == LoanApplicationStatus.APPROVED:
        # 获取发票
        invoice = await application.invoice
        
        # 创建贷款
        loan = await Loan.create(
            application_id=application.id,
            lender_id=current_user.id,
            interest_rate=5.0,  # 默认利率，实际应该由贷款方设置
            repayment_date=datetime.now() + timedelta(days=30),  # 默认还款日期
            amount=application.amount_requested,
            status=LoanStatus.ACTIVE
        )
        
        # 记录记账
        # 申请人账户增加贷款金额
        await record_credit(
            entity_id=application.applicant_id,
            amount=application.amount_requested,
            description=f"贷款批准: 申请ID {application.id}",
            reference_id=loan.id,
            reference_type="loan"
        )
        
        # 贷款方账户减少贷款金额
        await record_debit(
            entity_id=current_user.id,
            amount=application.amount_requested,
            description=f"发放贷款: 申请ID {application.id}",
            reference_id=loan.id,
            reference_type="loan"
        )
    
    return application


@router.get("/api/loans", response_model=List[LoanResponse])
async def get_loans(
    status: Optional[LoanStatus] = None,
    current_user: User = Depends(get_current_active_user)
):
    """获取贷款列表"""
    if current_user.role == UserRole.SUPPLIER or current_user.role == UserRole.BUYER:
        # 供应商和购买方只能看到自己作为申请人的贷款
        applications = await LoanApplication.filter(applicant_id=current_user.id).values_list("id", flat=True)
        query = Loan.filter(application_id__in=applications)
    elif current_user.role == UserRole.LENDER:
        # 贷款方只能看到自己作为贷款方的贷款
        query = Loan.filter(lender_id=current_user.id)
    else:
        # 管理员可以看到所有贷款
        query = Loan.all()
    
    if status:
        query = query.filter(status=status)
    
    loans = await query.order_by("-created_at").all()
    return loans


@router.get("/api/loans/{loan_id}", response_model=LoanResponse)
async def get_loan(
    loan_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """获取单个贷款"""
    loan = await Loan.get_or_none(id=loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="贷款不存在")
    
    application = await loan.application
    
    # 检查权限
    if current_user.role == UserRole.SUPPLIER or current_user.role == UserRole.BUYER:
        if application.applicant_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该贷款")
    elif current_user.role == UserRole.LENDER:
        if loan.lender_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权访问该贷款")
    
    return loan


@router.put("/api/loans/{loan_id}/repay")
async def repay_loan(
    loan_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """偿还贷款"""
    loan = await Loan.get_or_none(id=loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail="贷款不存在")
    
    application = await loan.application
    
    # 检查权限
    if current_user.role == UserRole.SUPPLIER or current_user.role == UserRole.BUYER:
        if application.applicant_id != current_user.id:
            raise HTTPException(status_code=403, detail="无权偿还该贷款")
    
    # 只有有效贷款可以偿还
    if loan.status != LoanStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="该贷款已偿还或违约")
    
    # 更新贷款状态为已偿还
    loan.status = LoanStatus.REPAID
    await loan.save()
    
    # 计算利息
    total_amount = loan.amount * (1 + loan.interest_rate / 100)
    
    # 记录记账
    # 申请人账户减少还款金额
    await record_debit(
        entity_id=application.applicant_id,
        amount=total_amount,
        description=f"偿还贷款: 贷款ID {loan.id}",
        reference_id=loan.id,
        reference_type="loan"
    )
    
    # 贷款方账户增加还款金额
    await record_credit(
        entity_id=loan.lender_id,
        amount=total_amount,
        description=f"收到贷款还款: 贷款ID {loan.id}",
        reference_id=loan.id,
        reference_type="loan"
    )
    
    return {
        "message": "贷款偿还成功",
        "loan_id": loan.id,
        "amount": loan.amount,
        "interest": loan.amount * (loan.interest_rate / 100),
        "total_repaid": total_amount
    }