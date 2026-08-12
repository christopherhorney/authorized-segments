# Authorized Segments Bulk Import

This project processes CSV files containing item-location-segment data and sends the data to an API in batches. It includes error handling, logging, and the ability to save payloads and responses for debugging.

## Prerequisites

- Python 3.8 or higher
- `pip` (Python package manager)
- Internet connection for API requests

## Installation

1. **Clone or Download the Repository**:
   - Clone the repository or download the project files to your local machine.

2. **Install Dependencies**:
   - Open a terminal in the project directory and run:
     ```bash
     pip install -r requirements.txt
     ```

3. **Set Up Environment Variables**:
   - Create a `.env` file in the project directory.
   - Add the following environment variable:
     ```
     ACCESS_TOKEN=your_api_access_token
     ```

4. **Prepare Input Files**:
   - Place your CSV files in the project directory.
   - Ensure the CSV files have the required columns:
     - `ITEM_ID`
     - `LOCATION_ID`
     - `AUTHORIZED_SEGMENTS`

## Usage

1. **Run the Script**:
   - Execute the script using:
     ```bash
     python segment_fixed.py
     ```

2. **Output**:
   - Processed data, payloads, responses, and summaries will be saved in the `bulk_import_output` folder.

3. **Dry Run**:
   - To test the script without sending API requests, set `DRY_RUN = True` in the script.

## Configuration

- Modify the following constants in `segment_fixed.py` as needed:
  - `BATCH_SIZE`: Number of records per API request.
  - `API_URL`: The API endpoint URL.
  - `REQUEST_TIMEOUT_SECONDS`: Timeout for API requests.
  - `SLEEP_BETWEEN_BATCHES_SECONDS`: Delay between batches.

## Error Handling

- Rows with missing or invalid data are logged in `skipped_rows.json` in the output folder.
- If `STOP_ON_ERROR = True`, the script stops on the first error.

## Notes

- Ensure the `ACCESS_TOKEN` is valid and has the necessary permissions for the API.
- The script assumes all rows in a CSV file have the same `LOCATION_ID`.

## License

This project is for internal use only. All rights reserved.

## Test Update
This is a git test.