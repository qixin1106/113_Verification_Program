from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from models import User, UserRole
from services.auth_service import get_password_hash, verify_password, create_access_token, decode_token
from config import settings
from datetime import datetime, timedelta
from tortoise.exceptions import DoesNotExist


router = APIRouter()
templates = Jinja2Templates(directory="templates")


# Pydantic模型
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


async def get_current_user_from_cookie(request: Request) -> Optional[User]:
    """从Cookie获取当前用户"""
    access_token = request.cookies.get("access_token")
    if not access_token:
        return None
    
    payload = decode_token(access_token)
    if not payload:
        return None
    
    username: str = payload.get("sub")
    role: str = payload.get("role")
    if username is None or role is None:
        return None
    
    user = await User.get_or_none(username=username)
    return user


async def get_current_user(token: str = Depends(lambda request: request.cookies.get("access_token")))
    """依赖注入获取当前用户"""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username: str = payload.get("sub")
    role: str = payload.get("role")
    if username is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌中缺少必要信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await User.get_or_none(username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="用户已禁用")
    return current_user


async def get_current_admin_user(current_user: User = Depends(get_current_active_user)):
    """获取当前管理员用户"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


async def get_current_supplier_user(current_user: User = Depends(get_current_active_user)):
    """获取当前供应商用户"""
    if current_user.role != UserRole.SUPPLIER:
        raise HTTPException(status_code=403, detail="需要供应商权限")
    return current_user


async def get_current_buyer_user(current_user: User = Depends(get_current_active_user)):
    """获取当前购买方用户"""
    if current_user.role != UserRole.BUYER:
        raise HTTPException(status_code=403, detail="需要购买方权限")
    return current_user


async def get_current_lender_user(current_user: User = Depends(get_current_active_user)):
    """获取当前贷款方用户"""
    if current_user.role != UserRole.LENDER:
        raise HTTPException(status_code=403, detail="需要贷款方权限")
    return current_user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """用户登录"""
    try:
        user = await User.get(username=username)
        if not verify_password(password, user.hashed_password):
            return templates.TemplateResponse(
                "login.html", 
                {"request": request, "error": "用户名或密码错误"}
            )
    except DoesNotExist:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "用户名或密码错误"}
        )
    if not user:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "用户名或密码错误"}
        )
    
    # 创建访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    
    # 设置Cookie并跳转到仪表板
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token", 
        value=access_token, 
        httponly=True, 
        max_age=access_token_expires.total_seconds()
    )
    response.set_cookie(key="username", value=user.username, max_age=access_token_expires.total_seconds())
    response.set_cookie(key="role", value=user.role, max_age=access_token_expires.total_seconds())
    
    return response


@router.post("/api/login", response_model=Token)
async def api_login(user_login: UserLogin):
    """API登录接口"""
    try:
        user = await User.get(username=user_login.username)
        if not verify_password(user_login.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/api/register", response_model=Token)
async def api_register(user_create: UserCreate, current_user: User = Depends(get_current_admin_user)):
    """API注册接口 (需要管理员权限)"""
    # 检查用户名是否已存在
    existing_user = await User.get_or_none(username=user_create.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 创建用户
    hashed_password = get_password_hash(user_create.password)
    user = await User.create(
        username=user_create.username,
        hashed_password=hashed_password,
        role=user_create.role,
        email=user_create.email,
        phone=user_create.phone,
        company_name=user_create.company_name
    )
    
    # 创建访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    """用户登出"""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("username")
    response.delete_cookie("role")
    return response


@router.post("/api/logout")
async def api_logout():
    """API登出接口"""
    return {"message": "登出成功"}


@router.post("/api/token/refresh", response_model=Token)
async def refresh_token(request: Request):
    """刷新令牌接口"""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username: str = payload.get("sub")
    role: str = payload.get("role")
    if username is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌中缺少必要信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await User.get_or_none(username=username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 创建新的访问令牌
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}