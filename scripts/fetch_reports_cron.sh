#!/bin/bash
# Automated GAM Report Fetching - Runs every 30 minutes
# Fetches reports for today's date for all active publishers

# Change to the backend directory
cd /home/ubuntu/MI-Backend

# Activate virtual environment
source venv/bin/activate

# Use America/New_York timezone to align with GAM reporting window
TODAY=$(TZ="America/New_York" date +%Y-%m-%d)
YESTERDAY=$(TZ="America/New_York" date -d "yesterday" +%Y-%m-%d)

# Log file
LOG_FILE="/home/ubuntu/MI-Backend/logs/cron-fetch-reports.log"

# Create logs directory if it doesn't exist
mkdir -p /home/ubuntu/MI-Backend/logs

# Run the report fetch command
echo "======================================" >> "$LOG_FILE"
echo "Report Fetch Started: $(date)" >> "$LOG_FILE"
echo "Dates: $YESTERDAY, $TODAY" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

python3 manage.py fetch_gam_reports \
    --date-from "$YESTERDAY" \
    --date-to "$YESTERDAY" \
    --parallel \
    --max-workers 2 \
    >> "$LOG_FILE" 2>&1

YESTERDAY_EXIT=$?

python3 manage.py fetch_gam_reports \
    --date-from "$TODAY" \
    --date-to "$TODAY" \
    --parallel \
    --max-workers 2 \
    >> "$LOG_FILE" 2>&1

TODAY_EXIT=$?

# Determine final exit code (non-zero if any run failed)
if [ $YESTERDAY_EXIT -ne 0 ] || [ $TODAY_EXIT -ne 0 ]; then
    EXIT_CODE=1
else
    EXIT_CODE=0
fi

echo "======================================" >> "$LOG_FILE"
echo "Report Fetch Completed: $(date)" >> "$LOG_FILE"
echo "Yesterday Exit Code: $YESTERDAY_EXIT" >> "$LOG_FILE"
echo "Today Exit Code: $TODAY_EXIT" >> "$LOG_FILE"
echo "Final Exit Code: $EXIT_CODE" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# Return exit code
exit $EXIT_CODE

