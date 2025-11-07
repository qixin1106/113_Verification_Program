from models import LoanApplication, Invoice, LoanApplicationStatus
from datetime import datetime


async def calculate_risk_score(application: LoanApplication) -> float:
    """计算贷款申请的风险评分 (0-100)"""
    # 基于发票年龄、金额、申请人历史等因素模拟风险评分
    invoice = await application.invoice
    if not invoice:
        return 50.0
    
    # 发票到期时间越近，风险越低
    days_until_due = (invoice.due_date - datetime.utcnow()).days
    days_until_due = max(days_until_due, 1)  # 避免除以0
    
    # 申请金额占发票金额的比例，比例越高风险越高
    amount_ratio = application.amount_requested / invoice.amount
    
    # 基础评分
    base_score = 70.0
    
    # 根据到期天数调整评分
    if days_until_due < 30:
        base_score += 15.0
    elif days_until_due < 60:
        base_score += 10.0
    elif days_until_due < 90:
        base_score += 5.0
    
    # 根据申请比例调整评分
    if amount_ratio <= 0.8:
        base_score += 10.0
    elif amount_ratio <= 1.0:
        base_score += 5.0
    elif amount_ratio <= 1.2:
        base_score -= 5.0
    else:
        base_score -= 20.0
    
    # 确保评分在0-100之间
    return max(0.0, min(100.0, base_score))


async def check_loan_eligibility(invoice_id: int, amount_requested: float) -> tuple[bool, str]:
    """检查贷款申请资格"""
    invoice = await Invoice.get_or_none(id=invoice_id)
    if not invoice:
        return False, "发票不存在"
    
    if invoice.status != "unpaid":
        return False, "只有未支付的发票才能申请贷款"
    
    # 检查申请金额是否超过发票金额的120%
    max_allowed = invoice.amount * 1.2
    if amount_requested > max_allowed:
        return False, f"申请金额不能超过发票金额的120% (最大允许: {max_allowed:.2f})"
    
    if amount_requested <= 0:
        return False, "申请金额必须大于0"
    
    # 检查是否已有未处理的贷款申请
    existing_applications = await LoanApplication.filter(
        invoice_id=invoice_id,
        status=LoanApplicationStatus.PENDING
    ).count()
    if existing_applications > 0:
        return False, "该发票已有未处理的贷款申请"
    
    return True, "符合贷款申请条件"


async def get_loan_application_summary(application: LoanApplication) -> dict:
    """获取贷款申请摘要"""
    invoice = await application.invoice
    applicant = await application.applicant
    
    summary = {
        "application_id": application.id,
        "applicant_id": applicant.id,
        "applicant_name": applicant.username,
        "invoice_id": invoice.id,
        "invoice_amount": invoice.amount,
        "amount_requested": application.amount_requested,
        "status": application.status,
        "risk_score": application.risk_score,
        "created_at": application.created_at
    }
    
    return summary