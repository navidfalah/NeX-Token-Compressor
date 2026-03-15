from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import settings
from api.routers import gateway
from api.routers import dashboard
from api.routers import accounts

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Enterprise AI Gateway"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="templates")

app.include_router(gateway.router)
app.include_router(dashboard.router)
app.include_router(accounts.router)

@app.get("/", response_class=HTMLResponse, name="landing")
async def home(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
