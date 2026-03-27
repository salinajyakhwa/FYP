# utils.py
import secrets
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from .models import EmailOTP

def generate_otp():
    return f"{secrets.randbelow(900000) + 100000}"

def send_otp(email, user=None):
    otp = generate_otp()
    expires_at = timezone.now() + timezone.timedelta(minutes=10)
    EmailOTP.objects.filter(email=email).delete()
    EmailOTP.objects.create(user=user, email=email, otp=otp, expires_at=expires_at)
    send_mail(
        'Your OTP Code',
        f'Your OTP code is {otp}. It will expire in 10 minutes.',
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
