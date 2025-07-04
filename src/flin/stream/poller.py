import requests
import pandas as pd
import time
import sys
import json

# We are running inside a Docker container. The 'src' folder is in the path.
from flin.preprocess import preprocess
from flin.clean_features import add_advanced_features

# This is the most important change. We now poll our own simulator.
# We use the service name 'simulator' because Docker Compose creates a private
# network where services can talk to each other using their names.
SIMULATOR_URL = "http://simulator:9090/get_latest_lap"

def poll_and_process():
    """
    Main loop to poll the simulator and process the data.
    """
    print("--- F1 Poller starting ---")
    print(f"Connecting to simulator at: {SIMULATOR_URL}")
    
    while True:
        try:
            response = requests.get(SIMULATOR_URL)

            # 200 OK: We received a lap
            if response.status_code == 200:
                # The response text is a JSON string '[{...}]'
                # We use pandas to read it directly into a DataFrame
                lap_df = pd.read_json(response.text, orient='records')

                # The JSON conversion turns Timedeltas into numbers (nanoseconds).
                # We need to convert them back for the processing functions to work.
                for col in ['LapTime', 'Sector1Time', 'Sector2Time', 'Sector3Time', 'PitInTime', 'PitOutTime', 'LapStartTime']:
                    if col in lap_df.columns:
                        lap_df[col] = pd.to_timedelta(lap_df[col], unit='ns')
                
                # Now we can process this lap using your functions
                processed_lap, _ = preprocess(lap_df.copy())

                if not processed_lap.empty:
                    featured_lap = add_advanced_features(processed_lap)
                    driver = featured_lap['Driver'].iloc[0]
                    lap_num = featured_lap['LapNumber'].iloc[0]
                    print(f"\nSuccessfully processed Lap {lap_num} for {driver}")
                else:
                    print("\nLap was valid but filtered out during preprocessing.")

            # 404 Not Found: The race replay is over
            elif response.status_code == 404:
                print("Race replay finished. Poller stopping.")
                break
            
            # Handle other potential errors
            else:
                print(f"Received unexpected status code: {response.status_code}")
                time.sleep(10)

        except requests.exceptions.ConnectionError:
            print("Simulator not ready... waiting to connect.")
            time.sleep(5)
            
        # Wait for 5 seconds before asking for the next lap
        time.sleep(5)

if __name__ == "__main__":
    poll_and_process()