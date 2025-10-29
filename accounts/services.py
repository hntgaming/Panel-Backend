from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_welcome_email_with_reset_link(user):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    # ✅ MATCHES frontend route
    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"

    # Prepare context for template
    context = {
        'user_name': user.get_full_name() or user.username,
        'user_email': user.email,
        'reset_url': reset_url,
    }

    # Render HTML template
    html_content = render_to_string('emails/welcome_email.html', context)
    
    # Create plain text version
    text_content = f"""
Hi {user.get_full_name() or user.username},

Welcome to HNT Gaming's AdTech Platform!

You've been granted access to our powerful Google Ad Manager integration system.

Set your password: {reset_url}

Features:
- Real-time revenue analytics and reporting
- Automated revenue sharing calculations
- Advanced GAM integration and optimization
- Secure payment management system
- Lightning-fast data processing

This link is valid for 24 hours. If you didn't request this invitation, please ignore this email.

Best regards,
HNT Gaming Team
    """

    # Create email
    subject = "🚀 Welcome to HNT Gaming - AdTech Platform"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    # Create multipart email
    msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    msg.attach_alternative(html_content, "text/html")
    
    # Send email
    msg.send(fail_silently=False)
