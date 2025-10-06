# 🎯 GAM Sentinel - Backend API

> **Advanced AdTech Reporting Platform by H&T Gaming**

Production-grade Django REST API for Google Ad Manager (GAM) SOAP reporting, real-time analytics, smart alerts, and multi-tier access control.

---

## 🚀 Features

### 📊 **GAM Reporting Engine**
- Real-time GAM SOAP API integration (v202508)
- Multi-dimensional report generation
- Parallel processing with 100 max workers
- Automated cron jobs (30-minute intervals)
- Service account authentication

### 🔐 **3-Tier Permission System**
- **Admin Users**: Full platform access
- **Parent Network Users**: Network-scoped access
- **Partner Users**: Assignment-based permissions
- Permission caching with auto-invalidation
- Role-based queryset filtering

### 🔔 **Smart Alerts & Tickets**
- 7 configurable alert types
- Automatic ticket creation
- Email notifications (HTML + plain text)
- Slack webhook integration
- SLA tracking and monitoring

### 👥 **User & Account Management**
- MCM invitation workflow
- Partner assignment system
- Parent network user creation
- Service account monitoring
- YAML configuration per network

---

## 🛠️ Tech Stack

- **Framework**: Django 4.2+
- **API**: Django REST Framework (DRF)
- **Authentication**: JWT (Simple JWT)
- **Database**: PostgreSQL
- **Cache**: Django Cache Framework
- **GAM Integration**: googleads library (SOAP API v202508)
- **Task Scheduling**: Cron + flock
- **Email**: Django Email Backend
- **Webhooks**: Slack Integration
- **CORS**: django-cors-headers
- **Environment**: python-decouple

---

## 📁 Project Structure

```
backend/
├── accounts/                    # User authentication & permissions
│   ├── models.py               # User, PartnerPermission
│   ├── permissions.py          # Permission helpers & mixins
│   ├── signals.py              # Cache invalidation
│   ├── views.py                # Auth endpoints
│   └── management/commands/
│       └── setup_parent_users.py
├── gam_accounts/               # GAM network management
│   ├── models.py               # GAMNetwork, MCMInvitation
│   ├── services.py             # MCM service logic
│   ├── views.py                # GAM endpoints
│   └── gam_config.py           # GAM configuration
├── reports/                    # Main reporting engine
│   ├── models.py               # MasterMetaData, ReportSyncLog
│   ├── services.py             # GAM report fetching
│   ├── views.py                # Report endpoints
│   └── management/commands/
│       └── fetch_gam_reports.py
├── sub_reports/                # Sub-report generation
│   ├── models.py               # SubReportData
│   ├── services.py             # Sub-report logic
│   └── views.py                # Sub-report endpoints
├── smart_alerts/               # Alert system
│   ├── models.py               # AlertRule, AlertLog
│   ├── alert_rules.py          # Alert implementations
│   ├── email_templates.py      # Email template manager
│   ├── slack_service.py        # Slack integration
│   └── management/commands/
│       └── run_smart_alerts.py
├── tickets/                    # Ticket management
│   ├── models.py               # Ticket, TicketComment
│   ├── views.py                # Ticket endpoints
│   └── serializers.py          # Ticket serializers
├── multigam/                   # Django project settings
│   ├── settings.py             # Main configuration
│   ├── urls.py                 # URL routing
│   └── permission.md           # Permission blueprint
├── yaml_files/                 # GAM network YAML configs
├── requirements.txt            # Python dependencies
└── manage.py                   # Django management
```

---

## 🔧 Installation & Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 14+
- Virtual environment
- Google Ad Manager service account (`key.json`)

### 1. Clone Repository
```bash
git clone https://github.com/hntgaming/Backend.git
cd Backend
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Create `.env` file in project root:
```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=api.hntgaming.me,13.201.117.27,localhost,127.0.0.1

# Database
DB_NAME=your_db_name
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_HOST=localhost
DB_PORT=5432

# CORS
CORS_ALLOWED_ORIGINS=https://api.hntgaming.me,https://report.hntgaming.me,http://localhost:3010
CORS_ALLOW_ALL_ORIGINS=False

# JWT
JWT_ACCESS_TOKEN_LIFETIME=120
JWT_REFRESH_TOKEN_LIFETIME=1440

# Email (Optional)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Slack Webhook (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 5. Database Setup
```bash
python manage.py migrate
```

### 6. Create Superuser
```bash
python manage.py createsuperuser
# Email: admin@gamplatform.com
# Password: AdminPass123!
```

### 7. Create Parent Users
```bash
python manage.py setup_parent_users
```

### 8. Setup Default Alert Rules
```bash
python manage.py setup_default_alerts
```

### 9. Place GAM Service Account Key
Place `key.json` in project root with service account credentials.

---

## 🚀 Running the Application

### Development Server
```bash
python manage.py runserver 0.0.0.0:8000
```

### Production (with Gunicorn)
```bash
gunicorn multigam.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

---

## ⏰ Cron Jobs

### GAM Reports Fetch (Every 30 minutes)
```bash
*/30 * * * * /home/ubuntu/gam-reports-cron.sh >> /home/ubuntu/gam-cron.log 2>&1
```

**Cron Script** (`gam-reports-cron.sh`):
- Fetches reports for all active accounts
- Processes 100 accounts in parallel
- Runs smart alerts after report fetch
- Sends email and Slack notifications
- Uses flock to prevent concurrent runs

### Manual Report Fetch
```bash
python manage.py fetch_gam_reports \
  --parallel \
  --max-workers 100 \
  --date-from 2025-10-01 \
  --date-to 2025-10-01
```

### Manual Alert Processing
```bash
python manage.py run_smart_alerts \
  --date-from 2025-10-01 \
  --date-to 2025-10-01 \
  --send-email
```

---

## 📡 API Endpoints

### Authentication
- `POST /api/auth/login/` - User login
- `POST /api/auth/register/` - User registration
- `GET /api/auth/me/permissions` - Get user permissions
- `POST /api/auth/logout/` - Logout
- `POST /api/auth/token/refresh/` - Refresh JWT token

### GAM Networks
- `GET /api/gam/networks/` - List GAM networks
- `POST /api/gam/networks/` - Create parent network
- `GET /api/gam/mcm-invitations/` - List invitations
- `POST /api/gam/mcm-invitations/manual-entry/` - Add child account

### Reports
- `POST /api/reports/query/` - Query report data
- `GET /api/reports/data/` - List report data
- `GET /api/reports/analytics/` - Analytics endpoint

### Sub-Reports
- `POST /api/sub-reports/query/` - Generate sub-report
- `GET /api/sub-reports/networks/` - List networks

### Smart Alerts
- `GET /api/smart-alerts/rules/` - List alert rules
- `POST /api/smart-alerts/rules/` - Create alert rule
- `PATCH /api/smart-alerts/rules/{id}/` - Update alert rule
- `GET /api/smart-alerts/logs/` - Get alert logs

### Tickets
- `GET /api/tickets/` - List tickets
- `POST /api/tickets/` - Create ticket
- `PATCH /api/tickets/{id}/` - Update ticket
- `GET /api/tickets/stats/` - Ticket statistics

### Partners
- `GET /api/auth/partners/` - List partners
- `PATCH /api/auth/users/{id}/permissions/` - Update permissions
- `GET /api/gam/partners/{id}/assigned-accounts/` - Get assigned accounts

---

## 🔐 Permission Types

```python
MANAGE_MCM_INVITES = 'manage_mcm_invites'
VERIFY_ACCOUNTS = 'verify_accounts'
ACCESS_REPORTS = 'access_reports'
MANAGE_ALERTS = 'manage_alerts'
ACCESS_TICKETS = 'access_tickets'
```

---

## 🗃️ Database Models

### Core Models
- **User**: Custom user with role-based access
- **PartnerPermission**: Permission assignments
- **GAMNetwork**: Parent and child networks
- **MCMInvitation**: MCM invitation tracking
- **AssignedPartnerChildAccount**: Partner-account assignments

### Reporting Models
- **MasterMetaData**: Main report data (all dimensions)
- **ReportSyncLog**: Sync history tracking
- **SubReportData**: Sub-report aggregations

### Alert & Ticket Models
- **AlertRule**: Alert rule configurations
- **AlertLog**: Alert trigger history
- **Ticket**: Support tickets
- **TicketComment**: Ticket comments
- **TicketSLA**: SLA tracking

---

## 🧪 Testing

### Run Tests
```bash
python manage.py test
```

### Test Coverage
```bash
coverage run --source='.' manage.py test
coverage report
```

---

## 📈 Performance Optimization

- **Queryset Optimization**: `select_related` and `prefetch_related`
- **Permission Caching**: 5-minute cache with auto-invalidation
- **Parallel Processing**: Up to 100 concurrent workers
- **Database Indexing**: Optimized indexes on frequently queried fields
- **API Pagination**: 20 items per page default

---

## 🔧 Management Commands

```bash
# Setup
python manage.py setup_parent_users       # Create parent network users
python manage.py setup_default_alerts     # Create default alert rules

# Reports
python manage.py fetch_gam_reports --help # Fetch GAM reports

# Alerts
python manage.py run_smart_alerts --help  # Process smart alerts
```

---

## 🐛 Troubleshooting

### Database Issues
```bash
python manage.py migrate
python manage.py showmigrations
```

### GAM Authentication Errors
- Check `key.json` is present
- Verify service account permissions
- Check `yaml_files/*.yaml` configurations

### Permission Issues
```bash
# Clear permission cache
python manage.py shell
>>> from django.core.cache import cache
>>> cache.clear()
```

---

## 📞 Production Server

**SSH Access:**
```bash
ssh -i "Test.pem" ubuntu@ec2-13-201-117-27.ap-south-1.compute.amazonaws.com
cd /home/ubuntu/Backend
source venv/bin/activate
```

**Deploy Updates:**
```bash
git pull origin main
python manage.py migrate
sudo systemctl restart gunicorn  # If using systemd
```

---

## 📊 Monitoring

### Logs
```bash
# Cron logs
tail -f /home/ubuntu/gam-cron.log

# Django logs (if configured)
tail -f logs/django.log

# System logs
journalctl -u gunicorn -f
```

### Health Checks
- Database connection test
- GAM API connectivity
- Service account status
- Permission cache status

---

## 🔒 Security

- ✅ JWT authentication
- ✅ Role-based access control (RBAC)
- ✅ Permission-based data filtering
- ✅ CORS configuration
- ✅ Secret key management
- ✅ SQL injection protection (Django ORM)
- ✅ XSS protection
- ✅ CSRF protection (admin only)

---

## 📄 Documentation

- `permission.md` - Permission system blueprint
- `README-SUB-REPORTS.md` - Sub-reports documentation
- `SLACK_SETUP.md` - Slack integration guide
- `Smart Alert Rules to Ticket Mapping.md` - Alert system docs

---

## 📞 Support

For issues or questions:
- Email: GAM-Sentinel@hntgaming.me
- Support: support@hntgaming.me

---

## 📄 License

© 2025 GAM Sentinel by H&T Gaming. All rights reserved.

---

**Built for production by H&T Gaming Team** 🚀

