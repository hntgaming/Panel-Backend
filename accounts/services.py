from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings


def send_welcome_email_with_reset_link(user):

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
    
    text_content = (
        f"Hi {user.get_full_name() or user.username},\n\n"
        "Welcome to the H&T GAMING Publisher Dashboard.\n\n"
        f"Activate your account: {reset_url}\n\n"
        "This link expires in 24 hours.\n"
        "If you didn't request this, email support@hntgaming.me\n\n"
        "— H&T GAMING\n"
        "support@hntgaming.me\n"
    )

    # Create email
    subject = "Welcome to H&T GAMING — Activate Your Account"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    # Create multipart email
    msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    msg.attach_alternative(html_content, "text/html")
    
    # Send email
    msg.send(fail_silently=False)
