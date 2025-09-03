from datetime import timedelta
from feast import FileSource, FeatureView, Field
from feast.types import Float32, Int64, String
from .entities import driver, grand_prix, lap_number

# Matches your parquet path and timestamp field
offline = FileSource(
    path="/opt/airflow/data/processed/clean_laps_*.parquet",
    timestamp_field="LapStartDate",   # must be tz-aware (UTC)
)

# IMPORTANT: schema must match columns in the parquet
lap_features = FeatureView(
    name="lap_features",
    entities=[driver, grand_prix, lap_number],
    ttl=timedelta(days=90),
    schema=[
        # numeric features
        Field(name="RacePct", dtype=Float32),
        Field(name="Position", dtype=Int64),
        Field(name="TyreLife", dtype=Float32),
        Field(name="PrevLapDT", dtype=Float32),
        Field(name="stint_lap", dtype=Int64),
        Field(name="PackCount_S3", dtype=Int64),
        Field(name="GapToLeader", dtype=Float32),
        Field(name="LastRacePace", dtype=Float32),
        Field(name="LapTime_lag1", dtype=Float32),
        Field(name="LapTime_lag2", dtype=Float32),
        Field(name="LapTime_lag3", dtype=Float32),
        Field(name="DirtyAir_lag1", dtype=Int64),
        Field(name="DirtyAir", dtype=Int64),
        Field(name="LeadLapTime", dtype=Float32),

        # categorical raw columns (your sklearn Pipeline handles encoding)
        Field(name="Driver", dtype=String),
        Field(name="Compound", dtype=String),
        Field(name="Team", dtype=String),
    ],
    online=True,
    source=offline,
)

