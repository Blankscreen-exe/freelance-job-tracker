from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from app.database import engine, Base
from app.routers import dashboard, workers, jobs, payments, settings, expenses, clients

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Upwork Tracker")

# Include routers
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(clients.router)
app.include_router(workers.router)
app.include_router(payments.router)
app.include_router(expenses.router)
app.include_router(settings.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
