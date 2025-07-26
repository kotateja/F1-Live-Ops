
import sys
import json
from great_expectations.data_context import DataContext

# --- 1. Read the checkpoint name and asset name from CLI arguments ---
if len(sys.argv) != 3:
    print("Usage: python check_ge.py <checkpoint_name> <asset_name>")
    sys.exit(1)

checkpoint_name = sys.argv[1]
asset_to_validate = sys.argv[2]

# --- 2. Initialize the Data Context ---
# This will find the great_expectations.yml file in the current directory
context = DataContext()

# --- 3. Run the Checkpoint ---
# The checkpoint from the file has a placeholder for the data_asset_name.
# We override it here by passing in a validations block, which is what the
# Airflow operator does via the `checkpoint_kwargs`.
result = context.run_checkpoint(
    checkpoint_name=checkpoint_name,
    validations=[
        {
            "batch_request": {
                "datasource_name": "processed_files",
                "data_connector_name": "processed_laps_connector",
                "data_asset_name": asset_to_validate,
                "batch_spec_passthrough": {
                    "reader_method": "parquet"
                }
            }
        }
    ]
)

# --- 4. Print the results ---
print(f"Validation successful: {result['success']}\n")
print("To see the full validation results, uncomment the line in check_ge.py")
# print(json.dumps(result.to_json_dict(), indent=2))

sys.exit(0 if result["success"] else 1)
