from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "F1-Live-Ops API is running!"}