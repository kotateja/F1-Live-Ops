# src/service/app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, pandas as pd
import mlflow
from mlflow import sklearn as mlflow_sklearn  # load raw sklearn model

app = FastAPI()

# Feature layout (order matters)
FEATURES = [
    "RacePct","Position","TyreLife","PrevLapDT","stint_lap",
    "PackCount_S3","GapToLeader","LastRacePace","IsFirstRaceOfSeason",
    "LapTime_lag1","LapTime_lag2","LapTime_lag3","DirtyAir_lag1","DirtyAir",
    "Driver","Compound","Team","LeadLapTime",
]
FLOAT_COLS = [
    "RacePct","Position","TyreLife","PrevLapDT","stint_lap",
    "PackCount_S3","GapToLeader","LastRacePace","IsFirstRaceOfSeason",
    "LapTime_lag1","LapTime_lag2","LapTime_lag3","DirtyAir_lag1","DirtyAir",
    "LeadLapTime",
]
CAT_COLS = ["Driver","Compound","Team"]

class PredictRequest(BaseModel):
    # numeric
    RacePct: float
    Position: int
    TyreLife: float
    PrevLapDT: float
    stint_lap: int
    PackCount_S3: int
    GapToLeader: float
    LastRacePace: float
    IsFirstRaceOfSeason: int
    LapTime_lag1: float
    LapTime_lag2: float
    LapTime_lag3: float
    DirtyAir_lag1: int
    DirtyAir: int
    # categorical
    Driver: str
    Compound: str
    Team: str
    # numeric
    LeadLapTime: float

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow-server:5000")
mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
MODEL_URI = "models:/f1-laptime-blend/Production"

# Load model once at startup (faster + avoids pyfunc dtype strictness)
try:
    model = mlflow_sklearn.load_model(MODEL_URI)
except Exception as e:
    raise RuntimeError(f"Could not load model from {MODEL_URI}: {e}")

@app.get("/")
def read_root():
    return {"message": "F1-Live-Ops API is running!"}

@app.post("/predict")
def predict(req: PredictRequest):
    try:
        # Build single-row frame in exact order
        row = pd.DataFrame([{k: getattr(req, k) for k in FEATURES}], columns=FEATURES)

        # Enforce dtypes expected by the sklearn pipeline
        for c in FLOAT_COLS:
            row[c] = pd.to_numeric(row[c], errors="coerce").astype("float64")
        for c in CAT_COLS:
            row[c] = row[c].astype(str)

        # Guard against accidental NaNs after coercion
        if row[FLOAT_COLS].isna().any().any():
            bad = row[FLOAT_COLS].columns[row[FLOAT_COLS].isna().any()].tolist()
            raise HTTPException(status_code=400, detail=f"Non-numeric values in {bad}")

        yhat = float(model.predict(row)[0])
        return {"prediction_seconds": yhat}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")
