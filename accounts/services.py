from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings

def send_welcome_email_with_reset_link(user):
    from django.contrib.auth.tokens import default_token_generator
    from django.urls import reverse
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.core.mail import send_mail

    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))

    # ✅ MATCHES frontend route
    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}"

    subject = "Welcome to GAM Platform - Set Your Password"
    message = (
        f"Hi {user.get_full_name() or user.username},\n\n"
        f"You’ve been invited to the GAM platform. Please set your password using the link below:\n\n"
        f"{reset_url}\n\n"
        f"If you weren’t expecting this, please ignore this email.\n\nThanks!"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
