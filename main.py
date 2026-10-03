"""
ShelfPulse - run the whole app:   uvicorn main:app --reload
Then open http://127.0.0.1:8000  (API docs at /docs)
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from archetype_api import router as archetype_router

BASE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="ShelfPulse", description="Why shoppers choose, reject and come back - by archetype.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(archetype_router)


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(BASE, "static", "index.html"))
