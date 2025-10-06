# Smart Alert Rules to Ticket Mapping - Implementation Complete ✅

## Overview
This document describes the 7 smart alert rules configured in the GAM Sentinel platform. All rules are active and automatically create tickets when triggered. Alert notifications are sent to **GAM-Seninal@hntgaming.me**.

---

## 1. Carrier Mismatch Alert 🌍

**Priority:** HIGH  
**Category:** Carrier Mismatch  
**Status:** ✅ Active

### Configuration
- **Dimension:** Country-Carrier (`country_carrier`)
- **Metric:** Total Impressions
- **Condition:** Custom logic - validates carrier-country combinations
- **Trigger:** When carrier from one country appears in a different country

### Examples
- ✅ **VALID:** Reliance Jio (India) appearing in India
- ❌ **ALERT:** Reliance Jio (India) appearing in UK → Creates HIGH priority ticket
- ❌ **ALERT:** AT&T (USA) appearing in Germany → Creates HIGH priority ticket

### Known Carrier-Country Mappings
- **India:** Reliance Jio, Airtel, Vodafone Idea, BSNL
- **USA:** AT&T, Verizon, T-Mobile, Sprint
- **UK:** Vodafone, O2, EE, Three
- **France:** Orange, SFR, Bouygues
- **Germany:** Telekom

### Detection Logic
```
For each country_carrier dimension record:
  1. Parse "Country | Carrier" from dimension_value
  2. Check if carrier is in known mappings
  3. If carrier is known, verify country matches expected countries
  4. If mismatch detected → Trigger alert
```

### Recommended Actions
1. Review traffic source for this carrier-country combination
2. Check if this is a known proxy/VPN provider
3. Consider blocking or monitoring this traffic source
4. Verify with partner if legitimate use case exists

---

## 2. Unknown Impressions Alert 🖥️

**Priority:** MEDIUM  
**Category:** Unknown Traffic  
**Status:** ✅ Active

### Configuration
- **Dimension:** Device Category (`deviceCategory`)
- **Dimension Value:** Desktop
- **Metric:** Unknown Impressions
- **Condition:** Greater Than (>)
- **Threshold:** 5.0% (percentage of total impressions)

### Trigger Condition
```
if (unknown_impressions / total_impressions) × 100 > 5.0%:
    → Create MEDIUM priority ticket
```

### Examples
- Total Impressions: 100,000
- Unknown Impressions: 6,000
- Unknown %: 6% → **ALERT TRIGGERED** ✅

### What it Indicates
- Potential issues with traffic source identification
- Device category detection problems
- Ad serving configuration issues

### Recommended Actions
1. Review desktop traffic sources
2. Check ad unit configurations
3. Verify GAM settings for device category tracking
4. Monitor trends over next few days

---

## 3. Unknown CPM Anomaly Alert 💰

**Priority:** HIGH  
**Category:** CPM Anomaly  
**Status:** ✅ Active

### Configuration
- **Dimension:** Overview
- **Metric:** eCPM
- **Condition:** Greater Than (>)
- **Threshold:** 2.0 (2× multiplier, 200% of normal)

### Trigger Condition
```
Normal eCPM = (total_revenue - unknown_revenue) / (total_impressions - unknown_impressions) × 1000
Unknown eCPM = (unknown_revenue / unknown_impressions) × 1000

if unknown_eCPM > (normal_eCPM × 2.0):
    → Create HIGH priority ticket
```

### Examples
- Normal eCPM: $5.00
- Unknown eCPM: $12.00
- Multiplier: 2.4x → **ALERT TRIGGERED** ✅

### What it Indicates
- Invalid traffic (IVT)
- Click fraud
- Bot activity
- Arbitrage attempts
- Data quality issues

### Recommended Actions
1. **URGENT:** Review unknown traffic sources immediately
2. Check for suspicious click patterns
3. Verify advertiser campaigns running
4. Consider pausing unknown traffic sources
5. Report to GAM for fraud investigation

---

## 4. Low Viewability Alert 👁️

**Priority:** HIGH  
**Category:** Viewability  
**Status:** ✅ Active

### Configuration
- **Dimension:** Overview
- **Metric:** Viewable Impressions Rate
- **Condition:** Less Than (<)
- **Threshold:** 25.0% (percentage)

### Trigger Condition
```
if viewability < 25.0% (and viewability > 0):
    → Create HIGH priority ticket
```

### Examples
- Viewability: 22%
- Threshold: 25% → **ALERT TRIGGERED** ✅

### Impact
- Advertiser satisfaction
- Campaign performance
- Revenue potential
- Platform reputation

### Recommended Actions
1. Review ad placement positions
2. Check page layout and above-the-fold content
3. Verify ad unit sizes and formats
4. Analyze traffic quality
5. Consider optimizing ad implementations

---

## 5. CTR Spike Alert 🖱️

**Priority:** MEDIUM  
**Category:** CTR Spike  
**Status:** ✅ Active

### Configuration
- **Dimension:** Overview
- **Metric:** CTR (Click-Through Rate)
- **Condition:** Greater Than (>)
- **Threshold:** 15.0% (percentage)

### Trigger Condition
```
if CTR > 15.0%:
    → Create MEDIUM priority ticket
```

### Examples
- CTR: 18%
- Threshold: 15% → **ALERT TRIGGERED** ✅

### What it Indicates
- Click fraud
- Bot activity
- Accidental clicks
- Invalid traffic (IVT)
- Misplaced ad units

### Recommended Actions
1. Review traffic sources for unusual patterns
2. Check for bot or scraper activity
3. Verify ad placement isn't deceptive
4. Analyze click timestamps for patterns
5. Consider implementing click fraud detection

---

## 6. Unfilled Impressions Alert 📉

**Priority:** MEDIUM  
**Category:** Unfilled Impressions  
**Status:** ✅ Active

### Configuration
- **Dimension:** Overview
- **Metric:** Fill Rate
- **Condition:** Less Than (<)
- **Threshold:** 90.0% (percentage)

### Trigger Condition
```
Fill Rate = (total_impressions / total_ad_requests) × 100

if fill_rate < 90.0% (i.e., unfilled > 10%):
    → Create MEDIUM priority ticket
```

### Examples
- Ad Requests: 100,000
- Impressions: 85,000
- Fill Rate: 85% → **ALERT TRIGGERED** ✅

### Impact
- Lost revenue opportunities
- Partner satisfaction
- Inventory utilization

### Recommended Actions
1. Review line item priorities and targeting
2. Check inventory availability
3. Verify ad unit configurations
4. Review price floors
5. Consider adding more demand sources

---

## 7. Service Account Inaccessible Alert 🔐

**Priority:** CRITICAL  
**Category:** Manual  
**Status:** ✅ Active

### Configuration
- **Dimension:** None (uses service account status)
- **Metric:** None (checks `service_account_enabled` field)
- **Condition:** Checks if service_account_enabled = False
- **Trigger:** When GAM account becomes inaccessible

### Trigger Condition
```
if service_account_enabled = False AND status IN ['invited', 'approved']:
    → Create CRITICAL priority ticket
```

### When it Triggers
- MCM invitation was revoked
- Account was closed
- Service account access was removed
- Network configuration changed
- Authentication errors (NO_NETWORKS_TO_ACCESS)

### **REQUIRED ACTION**
Remove the service account from GAM Network via GAM Admin interface.

### Steps to Resolve
1. Log into GAM admin
2. Navigate to Admin > Network Settings
3. Remove service account access for the affected network
4. Update invitation status in platform
5. Notify partner if necessary

---

## System Configuration

### Email Notifications
**All alerts send to:** GAM-Seninal@hntgaming.me

### Automation
- **Cron Schedule:** Every 30 minutes
- **Process Flow:**
  1. Fetch GAM reports for all accounts
  2. Run smart alert checks
  3. Create tickets for triggered alerts
  4. Send email summary

### Frontend Management
- **URL:** `/smart-alerts`
- **Features:**
  - View all alert rules
  - Edit thresholds, conditions, dimensions
  - Toggle active/inactive status
  - Create custom alert rules
  - View trigger statistics

### Threshold Input Formats
Alert rules support flexible threshold input:
- **Plain numbers:** `5`, `90`, `15.5`
- **Percentages:** `5%`, `90%`, `15%`
- **Multipliers:** `2x`, `1.5x`

All formats are automatically parsed to numeric values.

---

## Alert Rule Categories

### Metric-Based Rules (Editable Table)
1. Unknown Impressions Alert
2. Unknown CPM Anomaly Alert
3. Low Viewability Alert
4. CTR Spike Alert
5. Unfilled Impressions Alert

### System Rules (Separate Card, Toggle Only)
6. Service Account Inaccessible Alert
7. Carrier Mismatch Alert

---

## Database Schema

### AlertRule Model
- `name`: Alert rule name
- `description`: Description of what the alert monitors
- `target_type`: 'all_accounts' or 'specific_account'
- `target_account`: FK to MCMInvitation (optional)
- `metric`: Metric to monitor
- `dimension_type`: Dimension to filter on
- `dimension_value`: Specific dimension value (optional)
- `condition`: 'lt', 'gt', 'eq'
- `threshold`: Numeric threshold value
- `notification_emails`: Comma-separated email list
- `is_active`: Boolean
- `trigger_count`: Number of times triggered
- `last_triggered_at`: Timestamp of last trigger

### Ticket Model
- Auto-created from triggered alerts
- Includes alert context and recommended actions
- Linked to alert_rule_id
- Stores alert_trigger_data with metric values

---

## Management Commands

### Setup Default Rules
```bash
python manage.py setup_default_alerts
python manage.py setup_default_alerts --reset  # Delete and recreate
```

### Run Alert Checks Manually
```bash
python manage.py run_smart_alerts --date-from 2025-10-01 --date-to 2025-10-01 --send-email
```

---

## API Endpoints

### Alert Rules
- `GET /api/smart-alerts/rules/` - List all rules
- `POST /api/smart-alerts/rules/` - Create new rule
- `GET /api/smart-alerts/rules/{id}/` - Get rule details
- `PUT /api/smart-alerts/rules/{id}/` - Update rule
- `PATCH /api/smart-alerts/rules/{id}/` - Partial update
- `DELETE /api/smart-alerts/rules/{id}/` - Delete rule
- `PATCH /api/smart-alerts/rules/{id}/toggle/` - Toggle active status

### Tickets
- `GET /api/tickets/` - List tickets
- `POST /api/tickets/` - Create ticket
- `GET /api/tickets/{id}/` - Get ticket details
- `PATCH /api/tickets/{id}/` - Update ticket
- `PATCH /api/tickets/{id}/resolve/` - Resolve ticket
- `GET /api/tickets/stats/` - Get ticket statistics

---

## Implementation Status

✅ **Backend:**
- All 7 alert rules implemented
- Ticket auto-creation working
- Email notifications configured
- Cron integration complete
- Custom logic for each alert type

✅ **Frontend:**
- Smart Alerts page with full CRUD
- Tickets page with filtering
- Editable alert rules
- Percentage/multiplier support
- System rules separated

✅ **Production:**
- Deployed to server
- 7 rules active in database
- Cron running every 30 minutes
- All changes committed to GitHub

---

## Version History

**v1.0** - Initial implementation (Oct 1, 2025)
- All 7 alert rules configured
- Frontend UI complete
- Backend logic implemented
- Cron integration active
- Email notifications working

---

**Last Updated:** October 1, 2025  
**Status:** Production Ready ✅  
**Email:** GAM-Seninal@hntgaming.me
