from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

def role_required(allowed_roles=[]):
    """
    Decorator for views that checks that the user has one of the allowed roles.
    """
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            # Superusers have access to everything
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            try:
                if request.user.userprofile.role in allowed_roles:
                    return view_func(request, *args, **kwargs)
                else:
                    raise PermissionDenied
            except AttributeError: # Catches cases where UserProfile might not exist
                raise PermissionDenied

        return _wrapped_view
    return decorator
