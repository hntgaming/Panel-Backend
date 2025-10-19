# CORS Configuration for api2.hntgaming.me

## Summary
Backend CORS has been configured to accept requests only from the AWS Amplify deployed frontend at `publisher.hntgaming.me` and the API domain `api2.hntgaming.me`.

## Changes Made

### 1. Updated Django Settings
**File**: `multigam/settings.py`

#### CORS Allowed Origins
```python
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="https://api2.hntgaming.me,https://publisher.hntgaming.me,http://localhost:3010,http://127.0.0.1:3010"
).split(",")
```

#### Allowed Hosts
```python
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS', 
    default='api2.hntgaming.me,api.hntgaming.me,localhost,127.0.0.1,publisher.hntgaming.me,*.hntgaming.me'
).split(',')
```

## Configured Domains

### Production Domains
- ✅ `https://api2.hntgaming.me` - Primary API backend (with SSL)
- ✅ `https://publisher.hntgaming.me` - AWS Amplify frontend

### Development Domains
- ✅ `http://localhost:3010` - Local frontend development
- ✅ `http://127.0.0.1:3010` - Local frontend development (IP)

## CORS Headers Enabled

The backend now sends the following CORS headers:

```
Access-Control-Allow-Origin: https://publisher.hntgaming.me
Access-Control-Allow-Credentials: true
Access-Control-Allow-Headers: accept, accept-encoding, authorization, content-type, dnt, origin, user-agent, x-csrftoken, x-requested-with
Access-Control-Allow-Methods: DELETE, GET, OPTIONS, PATCH, POST, PUT
Access-Control-Max-Age: 86400
```

## Verification

### Test CORS Configuration
```bash
curl -s -H "Origin: https://publisher.hntgaming.me" \
     -H "Access-Control-Request-Method: POST" \
     -X OPTIONS \
     http://localhost:8000/api/auth/login/ -i
```

### Expected Response
```
HTTP/1.1 200 OK
access-control-allow-origin: https://publisher.hntgaming.me
access-control-allow-credentials: true
access-control-allow-methods: DELETE, GET, OPTIONS, PATCH, POST, PUT
```

## Frontend Configuration

### AWS Amplify Environment Variable
Set in AWS Amplify Console:

```
NEXT_PUBLIC_API_URL=https://your-backend-api-url.com/api
```

Replace `your-backend-api-url.com` with your actual backend domain.

## Security Features

- ✅ **Credentials Support**: `CORS_ALLOW_CREDENTIALS = True`
- ✅ **Specific Origins**: Only whitelisted domains allowed
- ✅ **All HTTP Methods**: GET, POST, PUT, PATCH, DELETE, OPTIONS
- ✅ **Custom Headers**: Authorization, Content-Type, etc.

## Production Deployment

When deploying to production:

1. **Update Backend URL**: Set `NEXT_PUBLIC_API_URL` in AWS Amplify
2. **Verify CORS**: Test API calls from frontend
3. **Check HTTPS**: Ensure all domains use HTTPS
4. **Monitor Logs**: Check for CORS-related errors

## Troubleshooting

### CORS Error in Browser
If you see CORS errors:

1. **Check Origin**: Verify the frontend domain matches configured origins
2. **Check Protocol**: Ensure using HTTPS (not HTTP) for production
3. **Check Headers**: Verify Authorization header is sent correctly
4. **Check Credentials**: Ensure `withCredentials: true` in Axios

### Backend Not Responding
1. **Check Server**: Ensure backend is running
2. **Check Firewall**: Verify port 8000 is accessible
3. **Check DNS**: Verify domain resolves correctly
4. **Check SSL**: Ensure SSL certificates are valid

## Status

🟢 **CORS Configured and Active**

- Backend: ✅ Configured
- Frontend: ✅ Ready for deployment
- Testing: ✅ Verified locally
- Production: ✅ Ready

## Repository Updates

- **Backend**: https://github.com/hntgaming/MI-Backend
  - Commit: "Add CORS configuration for publisher.hntgaming.me domain"
  
- **Frontend**: https://github.com/hntgaming/MI-Frontend
  - Commit: "Update deployment documentation with publisher.hntgaming.me domain"

---

**Last Updated**: October 8, 2025
**Domain**: publisher.hntgaming.me
**Status**: Production Ready ✅
