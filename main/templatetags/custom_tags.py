from django import template
from django.contrib.sites.shortcuts import get_current_site

try:
    from allauth.socialaccount.models import SocialApp
except Exception:  # pragma: no cover - keep templates safe if allauth changes
    SocialApp = None

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary:
        return dictionary.get(key)
    return None


@register.simple_tag(takes_context=True)
def social_provider_configured(context, provider):
    request = context.get('request')
    if not request or not SocialApp:
        return False

    site = get_current_site(request)
    return SocialApp.objects.filter(provider=provider, sites=site).exists()
