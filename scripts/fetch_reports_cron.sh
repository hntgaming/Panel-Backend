#!/bin/bash
# Automated GAM Report Fetching - Runs every 30 minutes
# Fetches reports for today's date for all active publishers

# Change to the backend directory
cd /home/ubuntu/MI-Backend

# Activate virtual environment
source venv/bin/activate

# Get today's date in YYYY-MM-DD format
TODAY=$(date +%Y-%m-%d)

# Log file
LOG_FILE="/home/ubuntu/MI-Backend/logs/cron-fetch-reports.log"

# Create logs directory if it doesn't exist
mkdir -p /home/ubuntu/MI-Backend/logs

# Run the report fetch command
echo "======================================" >> "$LOG_FILE"
echo "Report Fetch Started: $(date)" >> "$LOG_FILE"
echo "Date: $TODAY" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

python3 manage.py fetch_gam_reports \
    --date-from "$TODAY" \
    --date-to "$TODAY" \
    --parallel \
    --max-workers 2 \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

echo "======================================" >> "$LOG_FILE"
echo "Report Fetch Completed: $(date)" >> "$LOG_FILE"
echo "Exit Code: $EXIT_CODE" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Return exit code
exit $EXIT_CODE

