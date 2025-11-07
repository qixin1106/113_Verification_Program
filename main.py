import asyncio
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from tortoise.contrib.fastapi import register_tortoise
from tortoise import Tortoise
from tortoise.transactions import in_transaction
from models import User, UserRole, Order, Invoice, LoanApplication, Loan, AccountLedger
from services.auth_service import verify_password, get_password_hash, create_access_token
from config import settings
import os

# 创建FastAPI应用
app = FastAPI(
    title="供应链金融管理平台",
    description="解决供应链周期中回款慢的问题",
    version="1.0.0"
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置Jinja2模板
templates = Jinja2Templates(directory="templates")

# 注册Tortoise ORM
register_tortoise(
    app,
    db_url=settings.DB_URL,
    modules={"models": ["models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)

# 导入路由
from routers import auth, orders, invoices, loans, ledger, admin

app.include_router(auth.router, prefix="/auth", tags=["认证"])
app.include_router(orders.router, prefix="/orders", tags=["订单管理"])
app.include_router(invoices.router, prefix="/invoices", tags=["发票管理"])
app.include_router(loans.router, prefix="/loans", tags=["贷款管理"])
app.include_router(ledger.router, prefix="/ledger", tags=["记账系统"])
app.include_router(admin.router, prefix="/admin", tags=["管理员功能"])

# 首页路由
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/dashboard")

# 登录页面路由
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# 仪表板路由
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    username = request.cookies.get("username")
    role = request.cookies.get("role")
    
    if not username or not role:
        return RedirectResponse(url="/login")
    
    context = {
        "request": request,
        "username": username,
        "role": role
    }
    
    # 根据角色获取不同的数据
    if role == UserRole.admin:
        # 获取系统统计数据
        total_users = await User.all().count()
        total_suppliers = await User.filter(role=UserRole.supplier).count()
        total_buyers = await User.filter(role=UserRole.buyer).count()
        total_lenders = await User.filter(role=UserRole.lender).count()
        total_orders = await Order.all().count()
        total_invoices = await Invoice.all().count()
        total_loans = await Loan.all().count()
        total_pending_loan_applications = await LoanApplication.filter(status="pending").count()
        
        context["stats"] = {
            "total_users": total_users,
            "total_suppliers": total_suppliers,
            "total_buyers": total_buyers,
            "total_lenders": total_lenders,
            "total_orders": total_orders,
            "total_invoices": total_invoices,
            "total_loans": total_loans,
            "total_pending_loan_applications": total_pending_loan_applications
        }
    
    elif role == UserRole.supplier:
        # 获取供应商的订单和发票
        user = await User.get(username=username)
        orders = await Order.filter(supplier_id=user.id).all()
        invoices = await Invoice.filter(order__supplier_id=user.id).all()
        
        context["orders"] = orders
        context["invoices"] = invoices
    
    elif role == UserRole.buyer:
        # 获取购买方的订单和发票
        user = await User.get(username=username)
        orders = await Order.filter(buyer_id=user.id).all()
        invoices = await Invoice.filter(order__buyer_id=user.id).all()
        
        context["orders"] = orders
        context["invoices"] = invoices
    
    elif role == UserRole.lender:
        # 获取贷款方的贷款申请和贷款
        user = await User.get(username=username)
        loan_applications = await LoanApplication.filter(status="pending").all()
        loans = await Loan.filter(lender_id=user.id).all()
        
        context["loan_applications"] = loan_applications
        context["loans"] = loans
    
    return templates.TemplateResponse("dashboard.html", context)

# 登出路由
@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    response = RedirectResponse(url="/login")
    response.delete_cookie("username")
    response.delete_cookie("role")
    response.delete_cookie("access_token")
    return response

# 模拟支付回调
@app.post("/pay/mock")
async def mock_payment(invoice_id: int):
    """模拟支付回调，更新发票状态为已支付"""
    invoice = await Invoice.get_or_none(id=invoice_id)
    
    if not invoice:
        raise HTTPException(status_code=404, detail="发票不存在")
    
    if invoice.status == "paid":
        raise HTTPException(status_code=400, detail="发票已支付")
    
    # 更新发票状态
    invoice.status = "paid"
    await invoice.save()
    
    # 记录记账
    from services.ledger_service import record_transaction
    
    # 供应商收到款项，记贷方
    await record_transaction(
        entity_id=invoice.order.supplier_id,
        type="credit",
        amount=invoice.amount,
        description=f"收到订单 {invoice.order_id} 的付款",
        reference_id=invoice.id,
        reference_type="invoice"
    )
    
    # 购买方支付款项，记借方
    await record_transaction(
        entity_id=invoice.order.buyer_id,
        type="debit",
        amount=invoice.amount,
        description=f"支付订单 {invoice.order_id} 的款项",
        reference_id=invoice.id,
        reference_type="invoice"
    )
    
    return {"status": "success", "message": "支付成功", "invoice_id": invoice_id}

# 初始化数据
async def init_data():
    """初始化测试数据"""
    print("正在初始化测试数据...")
    
    # 检查是否已有数据
    user_count = await User.all().count()
    if user_count > 0:
        print("测试数据已存在，跳过初始化")
        return
    
    async with in_transaction():
        # 创建管理员
        admin_user = User(
            username="admin",
            role=UserRole.admin,
            hashed_password=get_password_hash("admin123")
        )
        await admin_user.save()
        
        # 创建供应商
        supplier = User(
            username="supplier",
            role=UserRole.supplier,
            hashed_password=get_password_hash("supplier123")
        )
        await supplier.save()
        
        # 创建购买方
        buyer = User(
            username="buyer",
            role=UserRole.buyer,
            hashed_password=get_password_hash("buyer123")
        )
        await buyer.save()
        
        # 创建贷款方
        lender = User(
            username="lender",
            role=UserRole.lender,
            hashed_password=get_password_hash("lender123")
        )
        await lender.save()
        
        # 创建测试订单
        order = Order(
            supplier_id=supplier.id,
            buyer_id=buyer.id,
            amount=10000.0,
            status="confirmed"
        )
        await order.save()
        
        # 创建测试发票
        invoice = Invoice(
            order_id=order.id,
            due_date="2024-12-31",
            amount=10000.0,
            status="unpaid"
        )
        await invoice.save()
        
        print("测试数据初始化完成")
        print("管理员账号: admin / admin123")
        print("供应商账号: supplier / supplier123")
        print("购买方账号: buyer / buyer123")
        print("贷款方账号: lender / lender123")

# 应用启动事件
@app.on_event("startup")
async def startup():
    await Tortoise.init(
        db_url=settings.DB_URL,
        modules={"models": ["models"]}
    )
    await Tortoise.generate_schemas()
    await init_data()

# 应用关闭事件
@app.on_event("shutdown")
async def shutdown():
    await Tortoise.close_connections()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)