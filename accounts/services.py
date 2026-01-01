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

Welcome to H&T GAMING Publisher Platform!

You've been granted access to our comprehensive Google Ad Manager integration system, designed to maximize your revenue through advanced programmatic advertising solutions.

Activate your account: {reset_url}

PLATFORM CAPABILITIES:
- Real-time revenue analytics and comprehensive reporting dashboards
- Advanced GAM integration with MCM (Multiple Customer Management)
- Advanced security and secure payment management
- High-performance infrastructure with sub-second response times

PREMIUM DEMAND PARTNERS:
- Access to premium programmatic demand sources including Google AdX, Google AdSense, and top-tier DSPs
- Optimized demand stack with real-time bidding (RTB) and private marketplace (PMP) deals
- Dynamic price floors and yield optimization for maximum revenue

HEADER BIDDING INTEGRATION:
- Prebid.js integration for simultaneous bid requests to multiple demand partners
- Server-side header bidding (SSHB) support for reduced latency
- Advanced bid management with timeout controls and price priority optimization
- Real-time bid analytics and performance monitoring

VIDEO ADVERTISING FORMATS:
- Instream Video Ads: Pre-roll, mid-roll, and post-roll video placements within video content players
- Outstream Video Ads: Standalone video units that play outside of video content (in-article, in-feed, floating players)
- VAST/VPAID compliant video ad serving with full IAB standards support
- Advanced video targeting, frequency capping, and viewability optimization

WHY CHOOSE H&T GAMING?
Our platform is built for publishers who demand the highest levels of performance, reliability, and revenue optimization. With our advanced AdTech stack, you'll have access to premium demand sources, cutting-edge header bidding technology, and comprehensive video ad solutions—all managed through an intuitive, powerful dashboard.

SECURITY NOTICE:
This activation link is valid for 24 hours. If you didn't request this invitation, please ignore this email or contact our support team immediately at ManagedInventory@hntgaming.me.

Ready to unlock the full potential of programmatic advertising? Click the link above to activate your account and start maximizing your ad revenue today!

Best regards,
H&T GAMING Team

---
Dashboard: https://publisher.hntgaming.me
Website: https://hntgaming.me
Support: ManagedInventory@hntgaming.me
© 2025 H&T GAMING. All rights reserved.
    """

    # Create email
    subject = "🚀 Welcome to H&T GAMING Publisher Platform"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_email = [user.email]

    # Create multipart email
    msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
    msg.attach_alternative(html_content, "text/html")
    
    # Send email
    msg.send(fail_silently=False)
