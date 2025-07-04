import fastapi
import uvicorn
import fastf1
import pandas as pd
import logging
import os

# --- This script is our fake "Live F1 API" ---
# It loads a real historical race and serves one lap at a time
# from a web endpoint, just like a real API would.

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI app
app = fastapi.FastAPI()

# Use an in-memory class to hold our data and state
class RaceReplayState:
    def __init__(self):
        self.laps_df = None
        self.current_lap_index = 0
        self.race_name = ""

state = RaceReplayState()

@app.on_event("startup")
async def load_race_data():
    """This function runs once when the server starts.
    It fetches and loads a historical race into memory.
    """
    logging.info("Simulator starting up: Loading historical race data...")
    try:
        # To avoid re-downloading every time, we'll use FastF1's cache
        # Make sure the cache directory exists
        cache_dir = os.path.expanduser('~/.fastf1_cache')
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        fastf1.Cache.enable_cache(cache_dir)
        logging.info(f"FastF1 cache enabled at: {cache_dir}")

        # Using a known, exciting race from a past season
        session = fastf1.get_session(2025, 1, 'R')
        session.load()
        
        # Sort laps by start time and then lap number to ensure correct replay order
        state.laps_df = session.laps.sort_values(by=['LapStartTime']).reset_index(drop=True)
        state.race_name = f"{session.event['EventName']} {session.event.year}"
        logging.info(f"Successfully loaded {len(state.laps_df)} laps from {state.race_name}.")
        
    except Exception as e:
        logging.error(f"FATAL: Failed to load race data for simulator: {e}")
        state.laps_df = pd.DataFrame() # Ensure it's an empty df on failure

@app.get("/get_latest_lap")
async def get_latest_lap():
    """This is our main API endpoint. Each time it's called,
    it returns the next lap in the race sequence.
    """
    if state.laps_df is None or state.laps_df.empty:
        return fastapi.responses.JSONResponse(
            content={"error": "Race data is not loaded."}, 
            status_code=503 # Service Unavailable
        )

    if state.current_lap_index >= len(state.laps_df):
        logging.info("Race replay finished. No more laps.")
        return fastapi.responses.JSONResponse(
            content={"message": "Race replay finished."},
            status_code=404 # Not Found
        )

    # Get the data for the next lap in the sequence
    next_lap = state.laps_df.iloc[[state.current_lap_index]]
    
    # Move the index forward for the next time this is called
    state.current_lap_index += 1

    # Convert the lap DataFrame row to a JSON string
    # We use `to_json` because it handles special data types like Timestamps
    lap_json_string = next_lap.to_json(orient='records', date_format='iso')
    
    # Return it as a proper JSON response
    return fastapi.responses.Response(content=lap_json_string, media_type="application/json")

# This allows running the simulator directly for testing, if needed
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)