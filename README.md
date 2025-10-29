# Managed Inventory Backend

## Project Overview
Django-based backend for the Managed Inventory system with GAM integration, publisher management, and automated report fetching.

## Tech Stack
- Django 4.2
- Python 3.8
- MySQL (RDS)
- Google Ad Manager API
- Gunicorn
- JWT Authentication
- CORS enabled

## Features
- Publisher/Admin user management
- GAM report fetching and processing
- Revenue sharing calculations
- Payment details management
- Automated cron jobs
- Financial summary API
- Role-based permissions

## Development
```bash
cd Backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Deployment
Push to GitHub and deploy to server:
```bash
cd Backend
git add .
git commit -m "Backend: [description]"
git push origin main
ssh -i "managed-inventory-key.pem" ubuntu@13.203.115.13 "cd /home/ubuntu/MI-Backend && git pull origin main && sudo systemctl restart gunicorn"
```

## Server Details
- Server: ubuntu@13.203.115.13
- Path: /home/ubuntu/MI-Backend
- Service: Gunicorn
- Database: MySQL RDS

## Repository
https://github.com/hntgaming/MI-Backend.git
