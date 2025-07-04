import pandas as pd
import sys

# Add the src directory to the Python path
sys.path.insert(0, './src')

from flin import etl_all, preprocess, clean_features, modelling

def main():
    """
    Runs the F1 data processing pipeline locally, simulating the Airflow DAG.
    """
    print("--- [Local Run] Starting Pipeline ---")

    # 1. Fetch Data (like fetch_data_task)
    print("\n--- 1. Fetching season data ---")
    laps_df = etl_all.fetch_season(year=2024)
    if laps_df.empty:
        print("No data fetched. Exiting.")
        return
    print(f"Fetched {len(laps_df):,} laps.")

    # 2. Process Data (like process_data_task)
    print("\n--- 2. Processing and Feature Engineering ---")
    
    # The bug was here: 'Deleted' column was float, not bool.
    # The fix in preprocess.py should resolve this.
    processed_laps, _, _, _, _ = preprocess.preprocess(laps_df)
    featured_laps = clean_features.add_advanced_features(processed_laps)
    
    print("\n--- 3. Training Models ---")
    # This function from your original code trains and tunes the models
    best_hgbr, best_lgb, _ = modelling.strict_train_tune(featured_laps)

    print("\n--- [Local Run] Pipeline Finished Successfully ---")
    print(f"Final processed dataset has {len(featured_laps):,} rows and {len(featured_laps.columns)} columns.")
    print("\nFirst 5 rows of the final dataframe:")
    print(best_hgbr,best_lgb)
    print(featured_laps.head())

if __name__ == "__main__":
    main()
