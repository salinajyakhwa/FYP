from .urls_admin import urlpatterns as admin_urlpatterns
from .urls_auth import urlpatterns as auth_urlpatterns
from .urls_payments import urlpatterns as payment_urlpatterns
from .urls_public import urlpatterns as public_urlpatterns
from .urls_traveler import urlpatterns as traveler_urlpatterns
from .urls_vendor import urlpatterns as vendor_urlpatterns

urlpatterns = (
    public_urlpatterns
    + auth_urlpatterns
    + traveler_urlpatterns
    + vendor_urlpatterns
    + admin_urlpatterns
    + payment_urlpatterns
)
