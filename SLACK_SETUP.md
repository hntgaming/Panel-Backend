# Slack Integration Setup for Smart Alerts

## Overview
GAM Sentinel can send beautiful alert notifications to Slack channels automatically when tickets are created. This guide shows how to set up Slack webhook integration.

---

## Step 1: Create Slack Incoming Webhook

### 1.1 Go to Slack App Directory
1. Visit: https://api.slack.com/apps
2. Click **"Create New App"**
3. Choose **"From scratch"**
4. Name your app: **"GAM Sentinel Alerts"**
5. Select your workspace

### 1.2 Enable Incoming Webhooks
1. In the left sidebar, click **"Incoming Webhooks"**
2. Toggle **"Activate Incoming Webhooks"** to ON
3. Click **"Add New Webhook to Workspace"**
4. Select the channel where you want alerts sent (e.g., `#gam-alerts`)
5. Click **"Allow"**

### 1.3 Copy Webhook URL
You'll see a webhook URL like:
```
https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXX
```

**Copy this URL** - you'll need it in the next step.

---

## Step 2: Configure Backend

### 2.1 Add to Environment Variables

On the production server, add the webhook URL to your `.env` file:

```bash
# SSH into server
ssh -i "Test.pem" ubuntu@ec2-13-201-117-27.ap-south-1.compute.amazonaws.com

# Edit .env file
cd /home/ubuntu/Backend
nano .env

# Add this line:
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 2.2 Restart Services
After adding the webhook URL, restart the Django application:

```bash
# If using systemd
sudo systemctl restart your-django-service

# If running manually
# Just restart the application
```

---

## Step 3: Test Slack Integration

### 3.1 Manual Test
Run the smart alerts command manually to test:

```bash
cd /home/ubuntu/Backend
source venv/bin/activate
python manage.py run_smart_alerts --date-from $(date +%Y-%m-%d) --date-to $(date +%Y-%m-%d) --send-email
```

### 3.2 Verify in Slack
Check your Slack channel - you should see:
- Individual alert notifications for each triggered alert
- Summary notification at the end with breakdown

---

## Slack Message Format

### Individual Alert Message
```
🔔 GAM SENTINEL ALERT - HIGH PRIORITY

Alert Title Here

ALERT DETAILS
─────────────
Ticket ID: #123
Category: 💰 CPM Anomaly
Network: 23128097909 - Publisher Name
Triggered: 2025-10-01 14:30:00

📊 Metrics:
• Observed: $12.50
• Threshold: $5.00

⚡ Recommended Actions:
• Review unknown traffic sources immediately
• Check for suspicious click patterns
• Verify advertiser campaigns running

[View Ticket] [View Alerts]
```

### Summary Message
```
✅ Smart Alerts Summary

Alerts Triggered: 5
Tickets Created: 5
Date Range: 2025-10-01 to 2025-10-01
Status: ⚠️ Action Required

Breakdown:
🌍 Carrier Mismatches: 2
🔐 Service Account Issues: 1
📊 Metric Alerts: 2

[View Tickets]
```

---

## Notification Triggers

Slack notifications are sent when:
1. **Individual Alerts**: Each time a ticket is created from an alert
2. **Summary**: After all alerts are processed (if any tickets were created)
3. **Critical Alerts**: Service account inaccessible (immediate notification)

---

## Customization

### Change Slack Channel
To send to a different channel, create a new webhook for that channel in Slack App settings.

### Disable Slack Notifications
Remove or comment out `SLACK_WEBHOOK_URL` from `.env` file. Email notifications will still work.

### Test Without Creating Tickets
```python
from smart_alerts.slack_service import slack_service

test_data = {
    'ticket_id': 999,
    'title': 'Test Alert',
    'priority': 'medium',
    'category': 'ctr_spike',
    'network_code': 'TEST123',
    'network_name': 'Test Network',
    'observed_value': '18%',
    'threshold_display': '15%',
    'triggered_at': '2025-10-01 14:30:00',
    'recommended_actions': ['Test action 1', 'Test action 2'],
    'dashboard_url': 'https://report.hntgaming.me'
}

slack_service.send_alert_notification(test_data)
```

---

## Automation

Once configured, Slack notifications are sent automatically:
- **Every 30 minutes** when the cron job runs
- **Integrated** with GAM reports fetch
- **No manual intervention** required

---

## Troubleshooting

### Notifications Not Appearing
1. **Check webhook URL**: Verify it's correctly set in `.env`
2. **Check channel permissions**: Ensure the app has access to the channel
3. **Check logs**: Look for errors in `/var/log/gam-reports/cron.log`
4. **Test manually**: Run `python manage.py run_smart_alerts --send-email`

### Webhook Expired
If your webhook stops working:
1. Go to Slack App settings
2. Regenerate the webhook URL
3. Update `.env` file with new URL
4. Restart services

---

## Benefits

✅ **Real-time Notifications**: Get alerts in Slack instantly  
✅ **Rich Formatting**: Beautiful, structured messages with Block Kit  
✅ **Actionable**: Direct links to dashboard and tickets  
✅ **Priority Colors**: Visual indication of severity  
✅ **Summary Reports**: Daily/periodic summaries of all alerts  
✅ **Team Collaboration**: Discuss alerts in thread  
✅ **Mobile Alerts**: Slack mobile app notifications  

---

## Security Notes

- **Keep webhook URL secret**: Don't commit it to Git
- **Use .env file**: Store in environment variables only
- **Rotate regularly**: Regenerate webhook URL periodically
- **Monitor usage**: Check Slack API rate limits

---

**Last Updated:** October 1, 2025  
**Status:** Production Ready ✅

