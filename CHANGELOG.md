# **Changelog**

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog,  
and this project adheres to Semantic Versioning.

## **\[Unreleased\]**

### V2
### **Added**

* **Prediction API (`/predict`):** Implemented the `src/service/app.py` endpoint that loads the Production model from the MLflow Model Registry (`models:/f1-laptime-blend/Production`), enforces strict feature order, coerces input types to the training schema, and returns `prediction_seconds`.
* **Dedicated MLflow image:** Introduced `Dockerfile.mlflow` and updated the `mlflow-server` service to build from this image with a proper `CMD` that runs the MLflow server against a local SQLite backend (`/mlflow/mlruns.db`) and filesystem artifacts store (`/mlflow/artifacts`) persisted via the `mlflow-data` volume.

### **Changed**

* **Airflow → Model registration flow:** Enhanced `train_model_task` to log both component models (HGBR pipeline, LightGBM wrapped with preprocessing), compute hold-out metrics, and register a blended sklearn model under `f1-laptime-blend` in MLflow.
* **Compose/MLflow hardening:** Moved `pip install mlflow` from container startup to build time for faster, more reliable boots (no network needed at runtime).
* **Inference environment parity:** Aligned scikit-learn versions across training (Airflow) and serving (app) to avoid pickle/ABI drift when loading the registered model.
* **App base image:** Installed `libgomp1` in the app image to satisfy LightGBM’s OpenMP runtime dependency during inference.

### **Fixed**

* **Unfitted blend during eval:** Resolved a `VotingRegressor NotFittedError` by removing reliance on an unfitted ensemble for prediction (use explicit average of component predictions or fit before use), while still logging the blended model artifact for registry serving.
* **Model load error at serve time:** Eliminated `_RemainderColsList` deserialization errors by pinning consistent scikit-learn versions between training and serving images.
* **LightGBM runtime:** Fixed `libgomp.so.1: cannot open shared object file` by adding `libgomp1` to the app container.
* **Request schema mismatch:** Fixed incompatible input types for column `Position` by coercing numerics in `/predict` to the expected floating-point types before invoking the model.

### V1
### **Changed**

*   **MLflow Integration:** Modified the `train_model_task` in `dags/nightly_retrain.py` to log model parameters, metrics, and artifacts to MLflow.
*   **Model Training Signature:** Updated the `strict_train_tune` function in `src/flin/modelling.py` to return model performance metrics (MAE) for logging.
*   **Local Runner Update:** Adjusted `dags/run_pipeline_locally.py` to align with the new return signature of the `strict_train_tune` function.
*   **Docker Compose Configuration:** Added an MLflow service (`mlflow-server`) to `docker-compose.yml` and configured the Airflow services to communicate with it.
*   **Model Training Optimization:** Reduced the grid search space for LightGBM in `src/flin/modelling.py` to improve training speed.
*   **Model Training Optimization:** Set `n_jobs=1` for `LGBMRegressor` in `src/flin/modelling.py` to prevent excessive resource consumption during training.
*   **DAG Consistency:** Updated `dags/run_pipeline_locally.py` and `dags/nightly_retrain.py` to align with the modified return signature of `modelling.strict_train_tune` after removing the LSTM model.
*   **Dependency pins for GE integration** Pinned `great-expectations==0.17.21` and `airflow-provider-great-expectations==0.3.0` to ensure API compatibility with the classic (v0.17) config and checkpoint flow.
*   **Great Expectations configuration aligned with GE 0.17.x**  
  * Updated `great_expectations/great_expectations.yml` to **`config_version: 3.0`** (required when using a `checkpoint_store` in GE 0.17.x).
  * Replaced all `FilesystemStoreBackend` occurrences with **`TupleFilesystemStoreBackend`** (the correct class for GE 0.17.x).
  * Explicitly defined default store names:
    * `expectations_store_name`, `validations_store_name`, `checkpoint_store_name`, `evaluation_parameter_store_name`.

* **Airflow DAG (nightly_retrain.py)**  
  * Rewrote the validation task to **not** call `context.run_checkpoint()` directly (which spawned a second, misconfigured context).  
    Instead, we now build and run an **ephemeral `Checkpoint` in code**, passing a **`RuntimeBatchRequest`** that points directly to the parquet path.
  * Added defensive logging and checks (showing asset name, parquet path, dir listing, and a head of the validated DataFrame).
  * Ensured **`reader_method: read_parquet`** (not `parquet`).

* **Airflow DB initialization line in docs/scripts**  
  * Clarified that the correct command is `airflow db upgrade` (not `db migrate`).

### **Removed**

*   **LSTM Model:** Removed the LSTM model training and evaluation sections from `src/flin/modelling.py` to reduce computational overhead and simplify the pipeline.
*   **Unused Imports:** Removed `torch` and related imports from `src/flin/modelling.py` as they are no longer needed after the LSTM model removal.

### **Added**

* **Airflow Integration:** Added Apache Airflow services (`postgres`, `airflow-webserver`, `airflow-scheduler`) to `docker-compose.yml` to enable workflow orchestration.
* **Airflow DAG (`dags/nightly_retrain.py`):** Created the first Airflow DAG to define the nightly model retraining pipeline. The DAG fetches, processes, and trains the model in a structured workflow.
* **Airflow User:** Created an initial admin user for the Airflow UI.
* **Airflow Dockerfile (`Dockerfile.airflow`):** Created a dedicated Dockerfile for Airflow to manage its specific dependencies and environment.
* **Airflow Admin User:** Manually created a new `admin` user to ensure reliable access to the Airflow UI.
### **Added**

* **Great Expectations Project Scaffolding:**  
  * Created the `great_expectations/` project with standard folders: `expectations/`, `checkpoints/`, `uncommitted/data_docs/`, `plugins/`.
  * Added initial suite `expectations/clean_laps_suite.json` (baseline expectations).
  * Added checkpoint `checkpoints/clean_laps_checkpoint.yml` (now used via an ephemeral, in-code checkpoint run).
  * Data Docs are written to `great_expectations/uncommitted/data_docs/local_site/`.

* **Great Expectations (GX) Validation in Airflow DAG:**  
  * Introduced a data validation step in `dags/nightly_retrain.py` that runs before model training.
  * Implemented a `RuntimeBatchRequest` + ephemeral checkpoint pattern to validate the exact parquet file produced by the pipeline, avoiding brittle regex/asset discovery and “empty batch_list” errors.
  * Added a runtime data connector (`default_runtime_data_connector_name`) to `great_expectations.yml` to support `RuntimeBatchRequest`.
  * Added a `checkpoint_store` and configured a persistent filesystem store for expectations, validations, and Data Docs.

* **Project-wide GE Environment Pinning:**  
  * Set `GREAT_EXPECTATIONS_HOME=/opt/airflow/great_expectations` in `docker-compose.yml` for both `airflow-webserver` and `airflow-scheduler` so every task loads the same GE project.
  * Deleted a stray `/opt/airflow/gx` GE project that was shadowing the real one inside containers.

* **Parquet Engine:**  
  * Added `pyarrow` to `requirements.txt` to ensure Great Expectations can read parquet files with `reader_method: read_parquet`.


### **Fixed**

*   **Airflow Database Initialization:** Replaced the deprecated `db init` command with `db migrate` in the startup process to ensure a stable and correct database schema setup.
*   **Airflow Security:** Resolved the "empty cryptography key" warning by generating and implementing a Fernet key. This secures sensitive data (e.g., connection credentials) stored in the Airflow database by enabling encryption. The key is managed securely via a `.env` file.
*   **Airflow Data Persistence:** Added a persistent named volume to the `postgres` service in `docker-compose.yml`. This ensures that the Airflow database (including users, connections, and task history) is saved permanently on the host machine and survives container restarts and rebuilds.
*   **Airflow Task Data Integrity:** Proactively fixed a data type issue in the `nightly_retrain_pipeline` DAG. Added a data type conversion step to explicitly convert all `Timedelta` and `Timestamp` columns back to their proper pandas types after they are passed between tasks. This prevents `AttributeError` exceptions caused by data serialization.
* **“no config_version key” / “UnsupportedConfigVersionError”**  
  Resolved by setting:
  * `great_expectations.yml` → `config_version: 3.0`,
  * `clean_laps_checkpoint.yml` → `config_version: 1.0`,
  * and pinning to `great-expectations==0.17.21`.

* **“The module … does not contain FilesystemStoreBackend”**  
  Fixed by switching to **`TupleFilesystemStoreBackend`**, which exists in GE 0.17.x.

* **“validation action_list cannot be empty”**  
  Added a valid `action_list` (store results, store evaluation params, update Data Docs) to `clean_laps_checkpoint.yml`.

* **“BatchRequest returned an empty batch_list”**  
  Eliminated by:
  * Returning the correct `asset_name` (filename **without** `.parquet`),
  * Installing a parquet engine (`pyarrow`),
  * Moving to a **RuntimeBatchRequest** that points at the exact parquet file,
  * And running an **ephemeral checkpoint** to avoid the second (fluent/empty) context.

* **Airflow Webserver 403 log & `secret_key` warning**  
    Set a shared `AIRFLOW__WEBSERVER__SECRET_KEY` and a `FERNET_KEY` in `docker-compose.yml` to fix authorization & encryption warnings.


### **Changed**

* **Docker Compose Configuration:** Modified `docker-compose.yml` to integrate the new Airflow services and use `Dockerfile.airflow` for building the Airflow images.

* **Dependency Management:** Updated `requirements.txt` to include all necessary libraries for `modelling.py`, `etl_all.py`, `preprocess.py`, and `clean_features.py`, as well as core MLOps tools (e.g., `matplotlib`, `seaborn`, `lightgbm`, `torch`, `mlflow`, `optuna`, `great-expectations`, `feast`, `apache-airflow`, `apache-airflow-providers-docker`, `pendulum`).
* **File Renaming:** Renamed `src/flin/etl-all.py` to `src/flin/etl_all.py` to resolve Python import errors in Airflow DAGs.

### **Removed**

## **\[0.1.0\] \- 2025-07-04**

This is the initial version of the F1-Live-Ops project, establishing the core MLOps foundation and a simulated live data pipeline.

### **Added**

* **Project Scaffolding:** Initialized the F1-Live-Ops repository with a src directory for application code and a simulator directory for the data replay service.  
* **Containerization (Dockerfile):** Created a Dockerfile that builds a Python 3.11-slim image, installs dependencies from requirements.txt, and sets up the application environment.  
* **Service Orchestration (docker-compose.yml):** Implemented a docker-compose.yml to define and run the two main services:  
  * app: The main application service, which will host the prediction API.  
  * simulator: The F1 race replay service.  
* **Live Data Simulator (simulator/replay.py):**  
  * Developed a FastAPI application to act as a realistic, controllable "live" data source.  
  * On startup, it loads a complete historical race session using the fastf1 library and its caching system.  
  * Exposes a /get\_latest\_lap endpoint that serves one lap of the race in JSON format per request, sequentially.  
* **Data Poller (src/flin/stream/poller.py):**  
  * Created a client script that continuously polls the simulator service.  
  * Handles JSON responses, correctly parsing them back into Pandas DataFrames with proper data types (e.g., Timedeltas).  
  * Successfully integrates and runs the migrated feature engineering pipeline (preprocess.py, clean\_features.py) on the received "live" data.  
* **Code Migration:** Migrated the core Python modules (preprocess.py, clean\_features.py, modelling.py, etl\_all.py) from the WeAreChecking-FastF1 project to provide the foundational data processing and modeling logic.  
* **Project Plan (GEMINI.md):** Created a comprehensive GEMINI.md file to serve as a master plan, documenting the project's architecture, goals, technology stack, and the pivot to a simulator-based approach.