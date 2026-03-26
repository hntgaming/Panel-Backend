#!/bin/bash
# Automated GAM Report Fetching - Runs every 30 minutes
# Fetches reports for today AND yesterday to catch any delayed/timezone data

cd /home/ubuntu/MI-Backend
source venv/bin/activate

TODAY=$(date +%Y-%m-%d)
YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)

LOG_FILE="/home/ubuntu/MI-Backend/logs/cron-fetch-reports.log"
mkdir -p /home/ubuntu/MI-Backend/logs

echo "======================================" >> "$LOG_FILE"
echo "Report Fetch Started: $(date)" >> "$LOG_FILE"
echo "Date range: $YESTERDAY to $TODAY" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

python3 manage.py fetch_gam_reports \
    --date-from "$YESTERDAY" \
    --date-to "$TODAY" \
    --parallel \
    --max-workers 8 \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

echo "======================================" >> "$LOG_FILE"
echo "Report Fetch Completed: $(date)" >> "$LOG_FILE"
echo "Exit Code: $EXIT_CODE" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

exit $EXIT_CODE
