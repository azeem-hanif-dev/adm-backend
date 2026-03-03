
from fastapi import FastAPI
from db import *

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Backend working on Vercel"}