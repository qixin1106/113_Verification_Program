from models import AccountLedger, LedgerType, User
from tortoise.transactions import in_transaction
from tortoise.functions import Sum


async def record_transaction(
    entity_id: int,
    type: LedgerType,
    amount: float,
    description: str,
    reference_id: int = None,
    reference_type: str = None
) -> AccountLedger:
    """记录交易"""
    async with in_transaction():
        ledger_entry = await AccountLedger.create(
            entity_id=entity_id,
            type=type,
            amount=amount,
            description=description,
            reference_id=reference_id,
            reference_type=reference_type
        )
        return ledger_entry


async def record_debit(
    entity_id: int,
    amount: float,
    description: str,
    reference_id: int = None,
    reference_type: str = None
) -> AccountLedger:
    """记录借方交易"""
    return await record_transaction(
        entity_id=entity_id,
        type=LedgerType.DEBIT,
        amount=amount,
        description=description,
        reference_id=reference_id,
        reference_type=reference_type
    )


async def record_credit(
    entity_id: int,
    amount: float,
    description: str,
    reference_id: int = None,
    reference_type: str = None
) -> AccountLedger:
    """记录贷方交易"""
    return await record_transaction(
        entity_id=entity_id,
        type=LedgerType.CREDIT,
        amount=amount,
        description=description,
        reference_id=reference_id,
        reference_type=reference_type
    )


async def calculate_balance(entity_id: int) -> float:
    """计算账户余额"""
    # 借方增加余额，贷方减少余额
    debit_total = await AccountLedger.filter(entity_id=entity_id, type=LedgerType.DEBIT).annotate(sum=Sum("amount")).values_list("sum", flat=True)
    credit_total = await AccountLedger.filter(entity_id=entity_id, type=LedgerType.CREDIT).annotate(sum=Sum("amount")).values_list("sum", flat=True)
    
    debit_sum = debit_total[0] if debit_total and debit_total[0] is not None else 0.0
    credit_sum = credit_total[0] if credit_total and credit_total[0] is not None else 0.0
    
    return debit_sum - credit_sum


async def get_ledger_entries(entity_id: int, limit: int = 100, offset: int = 0) -> list[AccountLedger]:
    """获取记账条目"""
    return await AccountLedger.filter(entity_id=entity_id).order_by("-created_at").limit(limit).offset(offset).all()


async def get_ledger_entries_by_reference(
    reference_id: int,
    reference_type: str,
    limit: int = 100,
    offset: int = 0
) -> list[AccountLedger]:
    """根据关联ID和类型获取记账条目"""
    return await AccountLedger.filter(
        reference_id=reference_id,
        reference_type=reference_type
    ).order_by("-created_at").limit(limit).offset(offset).all()