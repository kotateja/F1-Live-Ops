from fastapi import FastAPI
from feast import FeatureStore
import mlflow.pyfunc, pandas as pd, prometheus_client

LAT = prometheus_client.Summary("inference_latency_ms",
                                "Latency of inference endpoint in ms")

store = FeatureStore(repo_path="/app/feature_repo")
model = mlflow.pyfunc.load_model("models:/NextLap/Production")

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@LAT.time()
@app.get("/predict")
def predict(driver: str, lap_number: int):
    feats = store.get_online_features(
        entity_rows=[{"driver_id": driver, "lap_number": lap_number}],
        features=[
          "live_lap_features:LapTime_lag1",
          "live_lap_features:TyreLife",
          # …add the ones your model expects…
        ]
    ).to_df().drop(columns=["driver_id", "lap_number"])
    pred = model.predict(feats)[0]
    return {"predicted_lap_time": float(pred)}
