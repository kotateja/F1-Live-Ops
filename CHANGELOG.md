# **Changelog**

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog,  
and this project adheres to Semantic Versioning.

## **\[Unreleased\]**

### **Changed**

*   **Model Training Optimization:** Reduced the grid search space for LightGBM in `src/flin/modelling.py` to improve training speed.
*   **Model Training Optimization:** Set `n_jobs=1` for `LGBMRegressor` in `src/flin/modelling.py` to prevent excessive resource consumption during training.
*   **DAG Consistency:** Updated `dags/run_pipeline_locally.py` and `dags/nightly_retrain.py` to align with the modified return signature of `modelling.strict_train_tune` after removing the LSTM model.

### **Removed**

*   **LSTM Model:** Removed the LSTM model training and evaluation sections from `src/flin/modelling.py` to reduce computational overhead and simplify the pipeline.
*   **Unused Imports:** Removed `torch` and related imports from `src/flin/modelling.py` as they are no longer needed after the LSTM model removal.

### **Added**

* **Airflow Integration:** Added Apache Airflow services (`postgres`, `airflow-webserver`, `airflow-scheduler`) to `docker-compose.yml` to enable workflow orchestration.
* **Airflow DAG (`dags/nightly_retrain.py`):** Created the first Airflow DAG to define the nightly model retraining pipeline. The DAG fetches, processes, and trains the model in a structured workflow.
* **Airflow User:** Created an initial admin user for the Airflow UI.
* **Airflow Dockerfile (`Dockerfile.airflow`):** Created a dedicated Dockerfile for Airflow to manage its specific dependencies and environment.
* **Airflow Admin User:** Manually created a new `admin` user to ensure reliable access to the Airflow UI.

### **Fixed**

*   **Airflow Database Initialization:** Replaced the deprecated `db init` command with `db migrate` in the startup process to ensure a stable and correct database schema setup.
*   **Airflow Security:** Resolved the "empty cryptography key" warning by generating and implementing a Fernet key. This secures sensitive data (e.g., connection credentials) stored in the Airflow database by enabling encryption. The key is managed securely via a `.env` file.
*   **Airflow Data Persistence:** Added a persistent named volume to the `postgres` service in `docker-compose.yml`. This ensures that the Airflow database (including users, connections, and task history) is saved permanently on the host machine and survives container restarts and rebuilds.
*   **Airflow Task Data Integrity:** Proactively fixed a data type issue in the `nightly_retrain_pipeline` DAG. Added a data type conversion step to explicitly convert all `Timedelta` and `Timestamp` columns back to their proper pandas types after they are passed between tasks. This prevents `AttributeError` exceptions caused by data serialization.

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