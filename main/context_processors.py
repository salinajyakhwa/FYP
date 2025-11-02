from .models import UserProfile

def user_profile_context(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.userprofile
            return {'user_profile': profile}
        except UserProfile.DoesNotExist:
            return {}
    return {}
