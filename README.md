# H&T Gaming — Publisher Dashboard Backend

Django REST API powering the H&T Gaming Publisher Dashboard. Provides GAM (Google Ad Manager) integration, partner-admin/sub-publisher management, automated report fetching, earnings calculation, and role-based access control.

---

## Tech Stack

| Component | Version |
|-----------|---------|
| Python | 3.10+ |
| Django | 4.2.7 |
| Django REST Framework | 3.14.0 |
| Authentication | JWT (SimpleJWT 5.3) |
| Database | PostgreSQL (preferred) / MySQL |
| GAM API | google-ads-admanager (v202508) |
| Process Manager | Gunicorn |
| Task Scheduling | django-crontab |

---

## Architecture

```
multigam/            # Django project settings, root URLs, WSGI/ASGI
accounts/            # User management, RBAC, sites, payments, GAM credentials
  ├── models.py      # User, Permission, Site, PaymentDetail, GAMCredential, etc.
  ├── views.py       # Auth, profile, partner CRUD, sub-publisher, GAM connect
  ├── serializers.py # DRF serializers
  ├── urls.py        # /api/auth/* routes
  ├── permissions.py # Role-based permission classes
  └── services.py    # Business logic helpers
reports/             # GAM reporting, earnings, financial summaries
  ├── models.py      # MasterMetaData, ReportSyncLog, MonthlyEarning, SubPublisherEarning
  ├── views.py       # Report queries, analytics, dashboards, earnings CRUD
  ├── services.py    # GAM report fetch + storage pipeline
  ├── earnings_service.py  # Sub-publisher earnings calculation
  ├── gam_client.py  # GAM API client factory (per-partner credentials)
  └── urls.py        # /api/reports/* routes
core/                # Shared utilities
scripts/             # Cron helper scripts
yaml_files/          # GAM service account YAML configs
```

---

## Role Hierarchy

| Role | Description | Scope |
|------|-------------|-------|
| `admin` | Platform super-admin | Full access to all partners, reports, earnings, payments |
| `partner_admin` | Publisher partner | Connects own GAM, manages sites, sub-publishers, views reports |
| `sub_publisher` | Traffic partner / creator | Views filtered earnings for assigned subdomains only |

Sub-publishers are linked to a partner admin via `parent_publisher` FK. Reports are attributed to sub-publishers by matching their assigned subdomain against the GAM `site` dimension.

---

## API Endpoints

### Authentication (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/login/` | JWT login (returns access + refresh tokens) |
| POST | `/logout/` | Blacklist refresh token |
| POST | `/token/refresh/` | Refresh access token |
| GET/PUT | `/profile/` | View / update current user profile |
| POST | `/change-password/` | Change password |
| GET | `/me/permissions/` | Current user permissions + role flags |

### Partner Management (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/register/` | Create new partner admin (admin only) |
| GET | `/publishers/` | List all partner admins |
| PUT | `/publishers/<id>/` | Update partner admin details |
| DELETE | `/publishers/<id>/delete/` | Delete partner admin |
| GET | `/partners/` | List partners (minimal) |
| GET/PUT | `/partners/<id>/permissions/` | Manage partner permissions |

### Sub-Publisher Management (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/sub-publishers/` | List / create sub-publishers |
| GET/PUT/DELETE | `/sub-publishers/<id>/` | Sub-publisher detail operations |
| GET/POST/PUT | `/sub-publishers/<id>/tracking/` | Manage subdomain tracking assignment |
| GET/POST/DELETE | `/subdomains/` | Manage subdomains |

### GAM Credentials (`/api/auth/gam/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/status/` | GAM connection status |
| POST | `/connect/` | Connect GAM via service account |
| POST | `/test/` | Test GAM connection |
| POST | `/disconnect/` | Disconnect GAM account |
| POST | `/oauth/init/` | Start OAuth 2.0 flow |
| POST | `/oauth/callback/` | Complete OAuth 2.0 flow |

### Sites (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sites/` | List sites (admin: all, partner: own) |
| POST | `/sites/sync-status/` | Sync site statuses from GAM |

### Reports (`/api/reports/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/query/` | Unified report query with filters |
| GET | `/analytics/` | Aggregated analytics |
| GET | `/dashboard/` | Dashboard KPIs |
| GET | `/overview/` | Report overview |
| GET | `/detailed/` | Detailed report data |
| GET | `/export/` | Export reports |
| GET | `/financial-summary/` | Financial summary |
| POST | `/trigger-sync/` | Trigger GAM report sync |
| GET | `/sync-status/` | Check sync job status |
| GET | `/ivt/realtime/` | Real-time IVT check |

### Earnings (`/api/reports/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/earnings/` | List monthly earnings |
| POST | `/earnings/generate/` | Generate monthly earnings |
| PUT | `/earnings/bulk-update/` | Bulk update earnings |
| GET/PUT | `/earnings/<id>/` | Earnings detail |
| GET | `/sub-publisher-earnings/` | Sub-publisher earnings |
| POST | `/calculate-sub-publisher-earnings/` | Calculate sub-publisher earnings |
| GET | `/partner-rollup/` | Partner rollup summary |

### Payments (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST/PUT | `/payment-details/` | Current user payment details |
| GET | `/payment-details/all/` | All payment details (admin) |

### Tutorials (`/api/auth/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tutorials/` | List tutorials |
| POST | `/tutorials/create/` | Create tutorial (admin) |
| GET | `/tutorials/<slug>/` | Tutorial detail |

---

## Data Flow

```
Partner Admin connects GAM
        │
        ▼
GAMCredential stored (service account or OAuth 2.0)
        │
        ▼
fetch_gam_reports command (cron or manual trigger)
        │
        ▼
GAMClientService fetches reports per partner's GAM network
        │
        ▼
MasterMetaData records stored (per dimension, per date)
        │
        ▼
SubPublisherEarningsService matches subdomains → calculates earnings
        │
        ▼
Dashboard / Reports / Earnings pages display filtered data per role
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ (or MySQL 8+)
- GAM service account with API access

### Installation

```bash
cd Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
# Edit .env with your database, GAM, and email credentials
```

### Database

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_tutorials   # Optional: populate tutorial content
```

### Run Development Server

```bash
python manage.py runserver 8000
```

### GAM Report Sync

```bash
# Manual one-time sync
python manage.py fetch_gam_reports

# Cron setup (daily at 6 AM)
# Add to crontab: 0 6 * * * /path/to/scripts/fetch_reports_cron.sh
```

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Django secret key |
| `DB_ENGINE` | Yes | `postgresql` or `mysql` |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` | Yes | Database connection |
| `GAM_CLIENT_EMAIL` | Yes | Service account email for GAM API |
| `GAM_PRIVATE_KEY_FILE` | Yes | Path to service account JSON key |
| `CORS_ALLOWED_ORIGINS` | Yes | Comma-separated allowed origins |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Yes | SMTP credentials for emails |
| `SLACK_WEBHOOK_URL` | No | Slack alerts for sync failures |

---

## Deployment

### Production with Gunicorn

```bash
pip install gunicorn
gunicorn multigam.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Systemd Service

```ini
[Unit]
Description=H&T Publisher Dashboard Backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/Backend
ExecStart=/home/ubuntu/Backend/venv/bin/gunicorn multigam.wsgi:application --bind 0.0.0.0:8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

### Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ubuntu/Backend/staticfiles/;
    }
}
```

---

## Management Commands

| Command | Description |
|---------|-------------|
| `python manage.py fetch_gam_reports` | Fetch GAM reports for all connected partners |
| `python manage.py seed_tutorials` | Populate tutorial content for all roles |
| `python manage.py createsuperuser` | Create admin user |
