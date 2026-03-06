from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from app.database import engine, Base
from app.routers import dashboard, workers, jobs, payments, settings, expenses, clients, auth, users
from app.config import settings as app_settings
from app.config import BASE_DIR

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Upwork Tracker")

# Templates for error pages
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=app_settings.SECRET_KEY)

# Exception handler for 403 errors
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 403:
        return templates.TemplateResponse(
            "errors/403.html",
            {"request": request, "detail": exc.detail},
            status_code=403
        )
    # For other HTTP exceptions, use default behavior
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Include routers (auth first for home/login routes)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(clients.router)
app.include_router(workers.router)
app.include_router(payments.router)
app.include_router(expenses.router)
app.include_router(settings.router)
app.include_router(users.router)

# Auth middleware
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Allow public routes
    public_routes = ["/", "/login", "/static"]
    if any(request.url.path.startswith(route) for route in public_routes):
        return await call_next(request)
    
    # Check authentication for all other routes
    if not request.session.get("user_id"):
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)
    
    return await call_next(request)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
