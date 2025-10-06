# Managed Inventory Publisher Dashboard - Backend

A production-grade Django REST API backend for managing publisher inventory, revenue analytics, and adtech operations.

## 🚀 Features

### Core Functionality
- **Publisher Management**: Complete CRUD operations with revenue share configuration
- **Revenue Analytics**: Real-time financial reporting and calculations
- **GAM Integration**: Google Ad Manager API integration for report fetching
- **Role-Based Access Control**: Secure admin and publisher user management
- **Report Processing**: Advanced reporting with multiple dimensions and filtering

### Publisher Management
- ✅ User registration and authentication
- ✅ Publisher account creation with revenue share percentages
- ✅ Site URL and network ID management
- ✅ Role-based permissions (Admin/Publisher)
- ✅ Publisher deletion and account management

### Financial Analytics
- **Revenue Calculations**: Gross revenue, parent share, and publisher share
- **Real-time Reporting**: Live financial data from GAM API
- **Revenue Share Logic**: Configurable percentage-based calculations
- **Financial Summaries**: Comprehensive revenue breakdowns

### GAM Integration
- **Report Fetching**: Automated GAM report collection
- **Multi-Network Support**: Parent and child network management
- **YAML Configuration**: Flexible network configuration system
- **Data Processing**: Efficient report data processing and storage

## 🛠️ Technology Stack

- **Framework**: Django 5.1.2 with Django REST Framework
- **Database**: SQLite (development) / PostgreSQL (production)
- **Authentication**: JWT tokens with Simple JWT
- **GAM Integration**: Google Ad Manager API v202508
- **Task Processing**: Django management commands
- **API Documentation**: Auto-generated API docs

## 📦 Installation

### Prerequisites
- Python 3.13+
- pip package manager
- Google Ad Manager API credentials

### Setup
```bash
# Clone the repository
git clone <repository-url>
cd Backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Environment configuration
cp .env.example .env
# Edit .env with your configuration

# Database setup
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver 0.0.0.0:8000
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file in the Backend directory:

```env
# Django Configuration
DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1

# Database Configuration
DATABASE_URL=sqlite:///managed_inventory.db

# GAM Configuration
GAM_PARENT_NETWORK_CODE=152344380
GAM_CHILD_NETWORK_CODE=22878573653
GAM_API_VERSION=v202508
GAM_SERVICE_ACCOUNT_EMAIL=report@managed-inventory.iam.gserviceaccount.com
GAM_CREDENTIALS_FILE=key.json

# CORS Configuration
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3010
CORS_ALLOW_ALL_ORIGINS=True
CORS_ALLOW_CREDENTIALS=True
```

### GAM API Setup
1. Create a Google Cloud Project
2. Enable Google Ad Manager API
3. Create a service account
4. Download the JSON key file
5. Configure the service account in GAM
6. Place the key file in the Backend directory

## 📊 API Endpoints

### Authentication
- `POST /api/auth/login/` - User login
- `POST /api/auth/register/` - User registration
- `GET /api/auth/me/permissions/` - Get user permissions

### Publisher Management
- `GET /api/auth/publishers/` - List all publishers
- `POST /api/auth/publishers/` - Create new publisher
- `GET /api/auth/publishers/{id}/permissions/` - Get publisher permissions
- `PUT /api/auth/users/{id}/permissions/` - Update publisher permissions
- `DELETE /api/auth/publishers/{id}/delete/` - Delete publisher

### Reports & Analytics
- `POST /api/reports/query/` - Query report data
- `POST /api/reports/financial-summary/` - Get financial summary
- `GET /api/reports/` - List available reports
- `POST /api/reports/export/` - Export reports to CSV

## 🗄️ Database Models

### Core Models
- **User**: Publisher and admin user management
- **MasterMetaData**: Report data storage
- **ReportSyncLog**: Report synchronization tracking
- **PublisherAccountAccess**: Publisher access control

### User Model Fields
```python
class User:
    email = EmailField(unique=True)
    role = CharField(choices=[('admin', 'Admin'), ('publisher', 'Publisher')])
    revenue_share_percentage = DecimalField(default=10.00)
    site_url = URLField()
    network_id = CharField(max_length=100)
    is_active = BooleanField(default=True)
```

## 🔐 Security Features

- **JWT Authentication**: Secure token-based authentication
- **Role-Based Access Control**: Admin and publisher permissions
- **CORS Configuration**: Secure cross-origin requests
- **Input Validation**: Comprehensive data validation
- **SQL Injection Protection**: Django ORM protection

## 📈 Performance Optimizations

- **Database Indexing**: Optimized queries with proper indexing
- **Query Optimization**: Efficient database queries
- **Caching**: Redis caching for frequently accessed data
- **Pagination**: Efficient data pagination
- **Background Tasks**: Asynchronous report processing

## 🔄 GAM Integration

### Report Fetching
```python
# Fetch GAM reports
python manage.py fetch_gam_reports

# With date range
python manage.py fetch_gam_reports --start-date 2025-01-01 --end-date 2025-01-31
```

### Network Configuration
- **Parent Network**: Main GAM network for authentication
- **Child Networks**: Publisher-specific networks
- **YAML Files**: Network-specific configuration files
- **Service Account**: Shared authentication across networks

## 🛡️ Error Handling

- **API Error Responses**: Standardized error format
- **Logging**: Comprehensive logging system
- **Exception Handling**: Graceful error handling
- **Validation**: Input validation and sanitization

## 📊 Financial Calculations

### Revenue Share Logic
```python
# Parent share calculation
parent_share = gross_revenue * (revenue_share_percentage / 100)

# Publisher share calculation
publisher_share = gross_revenue - parent_share
```

### Supported Metrics
- Gross Revenue
- Impressions
- Clicks
- CTR (Click-Through Rate)
- eCPM (Effective Cost Per Mille)
- Fill Rate
- Viewability Rate

## 🚀 Production Deployment

### Database Migration
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic
```

### Environment Setup
- Configure production database (PostgreSQL recommended)
- Set up Redis for caching
- Configure proper CORS settings
- Set up monitoring and logging
- Configure SSL certificates

## 🔧 Management Commands

### Available Commands
- `fetch_gam_reports` - Fetch reports from GAM API
- `setup_parent_users` - Create parent user accounts
- `sync_parent` - Synchronize parent network data

### Usage Examples
```bash
# Fetch reports for specific date range
python manage.py fetch_gam_reports --start-date 2025-01-01 --end-date 2025-01-31

# Fetch reports with specific networks
python manage.py fetch_gam_reports --networks 152344380,22878573653
```

## 📱 API Documentation

### Request/Response Format
All API endpoints return JSON responses with the following structure:

```json
{
    "success": true,
    "data": {...},
    "message": "Operation completed successfully",
    "timestamp": "2025-01-01T00:00:00Z"
}
```

### Error Response Format
```json
{
    "success": false,
    "error": "Error message",
    "code": "ERROR_CODE",
    "timestamp": "2025-01-01T00:00:00Z"
}
```

## 🔄 Data Flow

1. **Authentication**: JWT token-based user authentication
2. **Authorization**: Role-based access control
3. **Data Processing**: Efficient query processing
4. **Response Formatting**: Standardized API responses
5. **Error Handling**: Comprehensive error management

## 📊 Monitoring & Logging

- **Application Logs**: Detailed application logging
- **API Logs**: Request/response logging
- **Error Tracking**: Comprehensive error tracking
- **Performance Monitoring**: API performance metrics

## 🛠️ Development

### Code Structure
```
Backend/
├── accounts/              # User management app
│   ├── models.py         # User and permission models
│   ├── views.py          # Authentication views
│   ├── serializers.py    # API serializers
│   └── permissions.py    # Custom permissions
├── reports/              # Reports app
│   ├── models.py         # Report data models
│   ├── views.py          # Report API views
│   ├── services.py       # GAM integration services
│   └── management/       # Management commands
├── multigam/             # Main project settings
│   ├── settings.py       # Django settings
│   ├── urls.py           # URL configuration
│   └── wsgi.py           # WSGI configuration
└── requirements.txt      # Python dependencies
```

### Testing
```bash
# Run tests
python manage.py test

# Run specific test
python manage.py test accounts.tests.UserTests
```

## 📞 Support

For technical support or feature requests, please contact the development team.

---

**Managed Inventory Publisher Dashboard Backend** - Production-grade Django API for adtech publisher management and revenue analytics.