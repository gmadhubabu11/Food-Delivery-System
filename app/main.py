import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.jobs.scheduler import create_scheduler
from app.routers import (
    addresses, admin, auth, cart, coupons, menu, orders, partners, ratings, reports,
    restaurant_orders, restaurants,
)
from app.websockets.manager import manager
from app.websockets.routes import router as ws_router

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager.set_loop(asyncio.get_running_loop())
    scheduler = None
    if settings.SCHEDULER_ENABLED:  # jobs start automatically with the app
        scheduler = create_scheduler()
        scheduler.start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Food Delivery System",
    description="Customers order from nearby restaurants, partners deliver with live tracking.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(restaurants.router)
app.include_router(menu.router)
app.include_router(addresses.router)
app.include_router(cart.router)
app.include_router(coupons.router)
app.include_router(orders.router)
app.include_router(restaurant_orders.router)
app.include_router(partners.router)
app.include_router(ratings.router)
app.include_router(reports.router)
app.include_router(ws_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", tags=["Health"])
def root():
    return {"service": "Food Delivery System", "docs": "/docs", "tracking_test_page": "/tracking-test"}


@app.get("/tracking-test", include_in_schema=False)
def tracking_test():
    return FileResponse(os.path.join(STATIC_DIR, "tracking_test.html"))
