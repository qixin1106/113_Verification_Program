from tortoise.models import Model
from tortoise.fields import (
    IntField,
    CharField,
    FloatField,
    DatetimeField,
    ForeignKeyField,
    EnumField,
    BooleanField,
    TextField
)
from tortoise import Tortoise
import enum
from datetime import datetime


# 时间戳模型基类
class TimeStampModel(Model):
    created_at = DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        abstract = True


# 用户角色枚举
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPPLIER = "supplier"
    BUYER = "buyer"
    LENDER = "lender"


# 订单状态枚举
class OrderStatus(str, enum.Enum):
    PENDING = "pending"  # 待确认
    CONFIRMED = "confirmed"  # 已确认
    PAID = "paid"  # 已支付


# 发票状态枚举
class InvoiceStatus(str, enum.Enum):
    UNPAID = "unpaid"  # 未支付
    PARTIAL = "partial"  # 部分支付
    PAID = "paid"  # 已支付


# 贷款申请状态枚举
class LoanApplicationStatus(str, enum.Enum):
    PENDING = "pending"  # 待审核
    APPROVED = "approved"  # 已批准
    REJECTED = "rejected"  # 已拒绝


# 贷款状态枚举
class LoanStatus(str, enum.Enum):
    ACTIVE = "active"  # 有效
    REPAID = "repaid"  # 已偿还
    DEFAULTED = "defaulted"  # 违约


# 记账类型枚举
class LedgerType(str, enum.Enum):
    DEBIT = "debit"  # 借方
    CREDIT = "credit"  # 贷方


# 用户模型
class User(TimeStampModel):
    id = IntField(pk=True, description="用户ID")
    username = CharField(max_length=50, unique=True, description="用户名")
    hashed_password = CharField(max_length=255, description="加密密码")
    role = EnumField(UserRole, default=UserRole.SUPPLIER, description="用户角色")
    email = CharField(max_length=100, unique=True, null=True, description="邮箱")
    phone = CharField(max_length=20, null=True, description="电话")
    company_name = CharField(max_length=100, null=True, description="公司名称")
    is_active = BooleanField(default=True, description="是否激活")

    class Meta:
        table = "users"
        indexes = [("username", "role")]


# 订单模型
class Order(TimeStampModel):
    id = IntField(pk=True, description="订单ID")
    supplier = ForeignKeyField("models.User", related_name="supplier_orders", description="供应商")
    buyer = ForeignKeyField("models.User", related_name="buyer_orders", description="购买方")
    amount = FloatField(description="订单金额")
    status = EnumField(OrderStatus, default=OrderStatus.PENDING, description="订单状态")
    description = TextField(null=True, description="订单描述")
    po_number = CharField(max_length=50, null=True, description="采购订单号")

    class Meta:
        table = "orders"
        indexes = [("supplier", "status"), ("buyer", "status"), ("created_at")]


# 发票模型
class Invoice(TimeStampModel):
    id = IntField(pk=True, description="发票ID")
    order = ForeignKeyField("models.Order", related_name="invoices", description="关联订单")
    due_date = DatetimeField(description="到期日期")
    amount = FloatField(description="发票金额")
    status = EnumField(InvoiceStatus, default=InvoiceStatus.UNPAID, description="发票状态")
    invoice_number = CharField(max_length=50, unique=True, description="发票号")
    remaining_amount = FloatField(description="剩余金额")

    class Meta:
        table = "invoices"
        indexes = [("order", "status"), ("due_date"), ("status")]


# 贷款申请模型
class LoanApplication(TimeStampModel):
    id = IntField(pk=True, description="贷款申请ID")
    applicant = ForeignKeyField("models.User", related_name="loan_applications", description="申请人")
    invoice = ForeignKeyField("models.Invoice", related_name="loan_applications", description="关联发票")
    amount_requested = FloatField(description="申请金额")
    status = EnumField(LoanApplicationStatus, default=LoanApplicationStatus.PENDING, description="申请状态")
    reason = TextField(null=True, description="申请理由")
    risk_score = FloatField(null=True, description="风险评分")

    class Meta:
        table = "loan_applications"
        indexes = [("applicant", "status"), ("invoice", "status"), ("status")]


# 贷款模型
class Loan(TimeStampModel):
    id = IntField(pk=True, description="贷款ID")
    application = ForeignKeyField("models.LoanApplication", related_name="loans", description="关联申请")
    lender = ForeignKeyField("models.User", related_name="loans", description="贷款方")
    interest_rate = FloatField(description="利率")
    repayment_date = DatetimeField(description="还款日期")
    amount = FloatField(description="贷款金额")
    status = EnumField(LoanStatus, default=LoanStatus.ACTIVE, description="贷款状态")

    class Meta:
        table = "loans"
        indexes = [("lender", "status"), ("repayment_date"), ("status")]


# 记账模型
class AccountLedger(TimeStampModel):
    id = IntField(pk=True, description="记账ID")
    entity = ForeignKeyField("models.User", related_name="ledger_entries", description="关联实体")
    type = EnumField(LedgerType, description="记账类型")
    amount = FloatField(description="金额")
    description = TextField(description="描述")
    reference_id = IntField(null=True, description="关联ID")
    reference_type = CharField(max_length=50, null=True, description="关联类型")

    class Meta:
        table = "account_ledger"
        indexes = [("entity", "type"), ("created_at"), ("reference_id", "reference_type")]


# 初始化Tortoise ORM配置
def get_tortoise_config(db_url: str):
    return {
        "connections": {
            "default": db_url
        },
        "apps": {
            "models": {
                "models": ["models", "aerich.models"],
                "default_connection": "default",
            },
        },
        "use_tz": False,
        "timezone": "Asia/Shanghai"
    }