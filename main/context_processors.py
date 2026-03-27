from .models import UserProfile, Notification

def user_profile_context(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.userprofile
            return {'user_profile': profile}
        except UserProfile.DoesNotExist:
            return {}
    return {}


def notification_context(request):
    if not request.user.is_authenticated:
        return {
            'unread_notification_count': 0,
        }

    return {
        'unread_notification_count': Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count(),
    }
