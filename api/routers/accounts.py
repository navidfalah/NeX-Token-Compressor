from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from api.dependencies import get_db
from models.accounts import User
from core.security import verify_password, create_access_token

router = APIRouter(tags=["Accounts"])
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse, name="accounts_login")
async def login_view(request: Request):
    return templates.TemplateResponse("accounts/login.html", {"request": request})

@router.post("/login", name="accounts_login_post")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user or not verify_password(password, user.password):
        return templates.TemplateResponse("accounts/login.html", {
            "request": request,
            "error": "Invalid username or password"
        })
    
    access_token = create_access_token(data={"sub": user.username})
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response

@router.get("/register", response_class=HTMLResponse, name="accounts_register")
async def register_view(request: Request):
    return templates.TemplateResponse("accounts/register.html", {"request": request})

@router.get("/logout", name="accounts_logout")
async def logout_view(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response
