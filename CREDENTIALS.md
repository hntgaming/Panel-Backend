# Managed Inventory Publisher Dashboard - Credentials

## Admin Login Credentials

### Frontend Login
- **URL**: https://publisher.hntgaming.me/login
- **Local URL**: http://localhost:3010/login

### Admin Account
```
Email: admin@test.com
Password: admin123
Role: Admin
```

### User Details
- **Full Name**: Test Admin
- **Company**: Test Company
- **Status**: Active
- **Permissions**: Full admin access

## Backend Access

### Django Admin Panel
- **URL**: http://localhost:8000/admin/
- **Production URL**: https://your-backend-domain.com/admin/

**Note**: The admin user above can also access the Django admin panel.

## API Endpoints

### Authentication
- **Login**: `POST /api/auth/login/`
- **Register**: `POST /api/auth/register/`
- **Permissions**: `GET /api/auth/me/permissions/`

### Example Login Request
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@test.com","password":"admin123"}'
```

### Example Response
```json
{
    "message": "Login successful",
    "user": {
        "id": 1,
        "email": "admin@test.com",
        "role": "admin",
        "is_admin_user": true
    },
    "tokens": {
        "refresh": "...",
        "access": "..."
    }
}
```

## Database

### SQLite Database
- **Location**: `Backend/managed_inventory.db`
- **Type**: SQLite (Development)

### Reset Admin Password
If you need to reset the admin password:

```bash
cd Backend
python3 manage.py shell -c "
from accounts.models import User
user = User.objects.get(email='admin@test.com')
user.set_password('your-new-password')
user.save()
print('Password updated!')
"
```

## Security Notes

⚠️ **Important Security Reminders**:

1. **Change Default Password**: Change the default password before deploying to production
2. **Strong Passwords**: Use strong, unique passwords for production
3. **Environment Variables**: Never commit credentials to Git
4. **HTTPS Only**: Always use HTTPS in production
5. **Regular Updates**: Regularly update passwords and review access

## Creating New Users

### Create Admin User
```bash
cd Backend
python3 manage.py createsuperuser
```

### Create Publisher User via API
```bash
curl -X POST http://localhost:8000/api/auth/register/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "email": "publisher@example.com",
    "password": "secure-password",
    "first_name": "Publisher",
    "last_name": "Name",
    "company_name": "Publisher Company",
    "role": "publisher",
    "revenue_share_percentage": 10.00,
    "site_url": "https://publisher-site.com",
    "network_id": "123456789"
  }'
```

## Access Levels

### Admin User
- ✅ Full system access
- ✅ View all publishers
- ✅ View all reports
- ✅ Create/edit/delete publishers
- ✅ Access Django admin panel
- ✅ Configure system settings

### Publisher User
- ✅ View own reports only
- ✅ View own financial data
- ✅ Update own profile
- ❌ Cannot view other publishers
- ❌ Cannot access admin panel
- ❌ Cannot create other users

## Testing Credentials

For testing purposes, you can use:

```
Email: admin@test.com
Password: admin123
```

**Remember to change these credentials in production!**

---

**Last Updated**: October 8, 2025
**Status**: Development Environment
**Security Level**: Development (Change for Production)
