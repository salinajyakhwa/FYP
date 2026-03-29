from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage

from .access import _get_vendor_or_403, _get_vendor_user  # noqa: F401


def send_vendor_status_email(request, vendor):
    user = vendor.user_profile.user
    current_site = get_current_site(request)

    if vendor.status == 'approved':
        subject = 'Your vendor account has been approved'
        body = (
            f"Hi {user.username},\n\n"
            "Your vendor application has been approved. "
            f"You can now log in and access the vendor portal at http://{current_site.domain}/login/.\n\n"
            "Regards,\nTravel Team"
        )
    elif vendor.status == 'rejected':
        rejection_reason = (vendor.rejection_reason or '').strip()
        subject = 'Your vendor application was rejected'
        body = (
            f"Hi {user.username},\n\n"
            "Your vendor application was reviewed and rejected. "
            f"{'Reason: ' + rejection_reason + '.\n\n' if rejection_reason else ''}"
            "If you believe this was a mistake, please contact the administrator.\n\n"
            "Regards,\nTravel Team"
        )
    else:
        return

    EmailMessage(subject, body, to=[user.email]).send()
