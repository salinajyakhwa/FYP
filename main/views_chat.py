from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ChatMessageForm
from .models import ChatThread, TravelPackage


@login_required
def chat_thread_open(request, package_id):
    from .views import _get_chat_thread_for_user_or_403  # noqa: F401

    package = get_object_or_404(
        TravelPackage.objects.select_related('vendor', 'vendor__user_profile', 'vendor__user_profile__user'),
        pk=package_id,
    )

    profile = getattr(request.user, 'userprofile', None)
    if not profile or profile.role != 'traveler':
        raise PermissionDenied

    thread, _ = ChatThread.objects.get_or_create(
        traveler=request.user,
        vendor=package.vendor,
        package=package,
        defaults={
            'booking': None,
            'custom_itinerary': None,
        }
    )
    return redirect('chat_thread_detail', thread_id=thread.id)


@login_required
def chat_thread_list(request):
    from .views import _get_vendor_or_403

    profile = getattr(request.user, 'userprofile', None)
    if not profile:
        raise PermissionDenied

    if profile.role == 'traveler':
        threads = ChatThread.objects.filter(
            traveler=request.user,
            is_active=True,
        ).select_related(
            'vendor',
            'vendor__user_profile',
            'vendor__user_profile__user',
            'package',
        ).prefetch_related('messages__sender')
    elif profile.role == 'vendor':
        vendor = _get_vendor_or_403(request)
        threads = ChatThread.objects.filter(
            vendor=vendor,
            is_active=True,
        ).select_related(
            'traveler',
            'package',
        ).prefetch_related('messages__sender')
    else:
        raise PermissionDenied

    return render(request, 'main/chat_thread_list.html', {
        'threads': threads,
        'user_role': profile.role,
    })


@login_required
def chat_thread_detail(request, thread_id):
    from .views import _get_chat_thread_for_user_or_403, _notify_chat_message

    thread = _get_chat_thread_for_user_or_403(request.user, thread_id)
    messages_qs = thread.messages.select_related('sender').all()

    if request.method == 'POST':
        form = ChatMessageForm(request.POST)
        if form.is_valid():
            message = form.save(commit=False)
            message.thread = thread
            message.sender = request.user
            message.save()
            ChatThread.objects.filter(pk=thread.id).update(updated_at=timezone.now())
            _notify_chat_message(message)
            return redirect('chat_thread_detail', thread_id=thread.id)
    else:
        form = ChatMessageForm()

    counterpart_name = thread.vendor.name if thread.traveler_id == request.user.id else thread.traveler.username
    return render(request, 'main/chat_thread_detail.html', {
        'thread': thread,
        'messages': messages_qs,
        'form': form,
        'counterpart_name': counterpart_name,
    })
