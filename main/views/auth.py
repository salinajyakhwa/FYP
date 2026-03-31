from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from django.contrib.auth import get_user_model

from ..forms import (
    CustomAuthenticationForm,
    CustomUserCreationForm,
    AccountDeletionRequestForm,
    PasswordChangeForm,
    ReactivateAccountForm,
    UserProfileUpdateForm,
    UserUpdateForm,
)
from ..models import EmailOTP, UserProfile
from ..services.accounts import (
    anonymize_user_account,
    deactivate_user_account,
    reactivate_user_account,
    traveler_can_be_deactivated,
    vendor_can_be_deactivated,
)
from ..utils import send_otp

User = get_user_model()
OTP_MAX_ATTEMPTS = 5
OTP_LOCKOUT_SECONDS = 600
OTP_RESEND_COOLDOWN_SECONDS = 60


def _mark_otp_sent(session):
    session['pending_otp_attempts'] = 0
    session['pending_otp_lockout_until'] = None
    session['pending_otp_last_sent_at'] = int(timezone.now().timestamp())


def _clear_pending_otp_state(session):
    session.pop('pending_otp_attempts', None)
    session.pop('pending_otp_lockout_until', None)
    session.pop('pending_otp_last_sent_at', None)


def _get_otp_state(request):
    now_ts = int(timezone.now().timestamp())
    lockout_until = request.session.get('pending_otp_lockout_until')
    last_sent_at = request.session.get('pending_otp_last_sent_at')

    lockout_remaining = max(0, int(lockout_until - now_ts)) if lockout_until else 0
    resend_remaining = max(0, OTP_RESEND_COOLDOWN_SECONDS - int(now_ts - last_sent_at)) if last_sent_at else 0

    return {
        'otp_attempts': request.session.get('pending_otp_attempts', 0),
        'otp_lockout_remaining': lockout_remaining,
        'resend_cooldown_remaining': resend_remaining,
        'otp_max_attempts': OTP_MAX_ATTEMPTS,
    }


class CustomLoginView(auth_views.LoginView):
    template_name = 'main/auth/login.html'
    authentication_form = CustomAuthenticationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                with transaction.atomic():
                    user = form.save()
                    send_otp(email, user)
            except Exception:
                messages.error(request, 'We could not send your OTP right now. Please try again.')
                return render(request, 'main/auth/register.html', {'form': form})

            request.session['pending_email'] = email
            request.session['pending_user_id'] = user.id
            _mark_otp_sent(request.session)
            messages.success(
                request,
                f"An OTP has been sent to {email}. Please enter it to complete registration.",
            )
            return redirect('verify_otp')
    else:
        initial_role = 'vendor' if request.GET.get('role') == 'vendor' else 'traveler'
        form = CustomUserCreationForm(initial={'role': initial_role})
    return render(request, 'main/auth/register.html', {'form': form})


def verify_otp(request):
    pending_email = request.session.get('pending_email')
    pending_user_id = request.session.get('pending_user_id')

    if not pending_email or not pending_user_id:
        messages.info(request, 'Start registration first to verify your email.')
        return redirect('register')

    otp_state = _get_otp_state(request)

    if request.method == 'POST':
        if otp_state['otp_lockout_remaining'] > 0:
            return render(request, 'main/auth/verify_otp.html', {
                'email': pending_email,
                'error': f"Too many incorrect attempts. Try again in {otp_state['otp_lockout_remaining']} seconds.",
                **otp_state,
            })

        otp = request.POST.get('otp', '').strip()
        otp_obj = (
            EmailOTP.objects
            .filter(email=pending_email, otp=otp, user_id=pending_user_id)
            .order_by('-created_at')
            .first()
        )

        if otp_obj and otp_obj.is_valid():
            user = get_object_or_404(User, pk=pending_user_id, email=pending_email)
            profile = get_object_or_404(UserProfile, user=user)
            user.is_active = True
            user.save(update_fields=['is_active'])
            profile.is_verified = True
            profile.save(update_fields=['is_verified'])

            EmailOTP.objects.filter(email=pending_email, user_id=pending_user_id).delete()
            request.session.pop('pending_email', None)
            request.session.pop('pending_user_id', None)
            _clear_pending_otp_state(request.session)

            vendor = getattr(profile, 'vendor', None)
            if profile.role == 'vendor' and vendor:
                vendor.status = 'pending'
                vendor.save(update_fields=['status'])
                messages.success(
                    request,
                    'Your email is verified. Your vendor application has been submitted for admin review.',
                )
                return redirect('login')

            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Your account has been verified successfully.')
            return redirect('dashboard')

        attempts = request.session.get('pending_otp_attempts', 0) + 1
        request.session['pending_otp_attempts'] = attempts
        if attempts >= OTP_MAX_ATTEMPTS:
            request.session['pending_otp_lockout_until'] = int(timezone.now().timestamp()) + OTP_LOCKOUT_SECONDS
            request.session['pending_otp_attempts'] = 0
            otp_state = _get_otp_state(request)
            error_message = (
                f"Too many incorrect attempts. OTP entry is locked for {otp_state['otp_lockout_remaining']} seconds."
            )
        else:
            remaining_attempts = OTP_MAX_ATTEMPTS - attempts
            otp_state = _get_otp_state(request)
            error_message = f"Invalid or expired OTP. You have {remaining_attempts} attempt(s) left."

        return render(request, 'main/auth/verify_otp.html', {
            'email': pending_email,
            'error': error_message,
            **otp_state,
        })

    return render(request, 'main/auth/verify_otp.html', {'email': pending_email, **otp_state})


def resend_otp(request):
    pending_email = request.session.get('pending_email')
    pending_user_id = request.session.get('pending_user_id')

    if request.method != 'POST':
        return redirect('verify_otp')

    if not pending_email or not pending_user_id:
        messages.info(request, 'Start registration first to request a new OTP.')
        return redirect('register')

    otp_state = _get_otp_state(request)
    if otp_state['otp_lockout_remaining'] > 0:
        messages.error(request, f"Too many incorrect attempts. Try again in {otp_state['otp_lockout_remaining']} seconds.")
        return redirect('verify_otp')

    if otp_state['resend_cooldown_remaining'] > 0:
        messages.error(request, f"Please wait {otp_state['resend_cooldown_remaining']} seconds before requesting a new OTP.")
        return redirect('verify_otp')

    user = get_object_or_404(User, pk=pending_user_id, email=pending_email)
    send_otp(pending_email, user)
    _mark_otp_sent(request.session)
    messages.success(request, 'A new OTP has been sent to your email.')
    return redirect('verify_otp')


@login_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    deactivate_form = AccountDeletionRequestForm(user=request.user)
    permanent_delete_form = AccountDeletionRequestForm(user=request.user)

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            profile_form = UserProfileUpdateForm(request.POST, request.FILES, instance=profile)
            pass_form = PasswordChangeForm(request.user)
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Your profile has been updated!')
                return redirect('profile')

        elif 'change_password' in request.POST:
            pass_form = PasswordChangeForm(request.user, request.POST)
            if pass_form.is_valid():
                user = pass_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Your password was successfully updated!')
                return redirect('profile')
            messages.error(request, 'Please correct the password error below.')
            user_form = UserUpdateForm(instance=request.user)
            profile_form = UserProfileUpdateForm(instance=profile)
            deactivate_form = AccountDeletionRequestForm(user=request.user)
            permanent_delete_form = AccountDeletionRequestForm(user=request.user)

        elif 'deactivate_account' in request.POST:
            user_form = UserUpdateForm(instance=request.user)
            profile_form = UserProfileUpdateForm(instance=profile)
            pass_form = PasswordChangeForm(request.user)
            deactivate_form = AccountDeletionRequestForm(request.POST, user=request.user)
            permanent_delete_form = AccountDeletionRequestForm(user=request.user)
            if deactivate_form.is_valid():
                reason = deactivate_form.cleaned_data['reason']

                if profile.role == 'vendor':
                    vendor = getattr(profile, 'vendor', None)
                    if not vendor:
                        messages.error(request, 'Vendor profile is incomplete.')
                    elif vendor.deletion_request_status == 'pending':
                        messages.info(request, 'Your vendor permanent deletion request is already pending admin review.')
                    else:
                        can_deactivate, blockers = vendor_can_be_deactivated(vendor)
                        if not can_deactivate:
                            messages.error(
                                request,
                                'You cannot deactivate your vendor account while you still have active packages, bookings, trips, disputes, or refunds in progress.',
                            )
                            return redirect('profile')
                        profile.account_deletion_reason = reason
                        profile.save(update_fields=['account_deletion_reason'])
                        deactivate_user_account(request.user)
                        logout(request)
                        messages.success(request, 'Your vendor account has been deactivated. You can reactivate it later if needed.')
                        return redirect('home')
                else:
                    can_deactivate, blockers = traveler_can_be_deactivated(request.user)
                    if not can_deactivate:
                        messages.error(
                            request,
                            'You cannot deactivate your account while you still have active bookings, trips, disputes, or refunds in progress.',
                        )
                        return redirect('profile')
                    profile.account_deletion_reason = reason
                    profile.save(update_fields=['account_deletion_reason'])
                    deactivate_user_account(request.user)
                    logout(request)
                    messages.success(request, 'Your account has been deactivated successfully.')
                    return redirect('home')
            else:
                messages.error(request, 'Please confirm your password to continue.')

        elif 'permanent_delete_account' in request.POST:
            user_form = UserUpdateForm(instance=request.user)
            profile_form = UserProfileUpdateForm(instance=profile)
            pass_form = PasswordChangeForm(request.user)
            deactivate_form = AccountDeletionRequestForm(user=request.user)
            permanent_delete_form = AccountDeletionRequestForm(request.POST, user=request.user)
            if permanent_delete_form.is_valid():
                reason = permanent_delete_form.cleaned_data['reason']

                if profile.role == 'vendor':
                    vendor = getattr(profile, 'vendor', None)
                    if not vendor:
                        messages.error(request, 'Vendor profile is incomplete.')
                    elif vendor.deletion_request_status == 'pending':
                        messages.info(request, 'Your vendor permanent deletion request is already pending admin review.')
                    else:
                        can_deactivate, blockers = vendor_can_be_deactivated(vendor)
                        if not can_deactivate:
                            messages.error(
                                request,
                                'You cannot request permanent deletion while you still have active packages, bookings, trips, disputes, or refunds in progress.',
                            )
                            return redirect('profile')
                        vendor.deletion_request_status = 'pending'
                        vendor.deletion_requested_at = timezone.now()
                        vendor.deletion_reason = reason
                        vendor.deletion_reviewed_at = None
                        vendor.deletion_review_notes = ''
                        vendor.save(update_fields=[
                            'deletion_request_status',
                            'deletion_requested_at',
                            'deletion_reason',
                            'deletion_reviewed_at',
                            'deletion_review_notes',
                        ])
                        messages.success(request, 'Your vendor permanent deletion request has been submitted for admin review.')
                        return redirect('profile')
                else:
                    can_deactivate, blockers = traveler_can_be_deactivated(request.user)
                    if not can_deactivate:
                        messages.error(
                            request,
                            'You cannot request permanent deletion while you still have active bookings, trips, disputes, or refunds in progress.',
                        )
                        return redirect('profile')
                    profile.account_deletion_requested_at = timezone.now()
                    profile.account_deletion_reason = reason
                    profile.account_deletion_request_status = 'pending'
                    profile.account_deletion_reviewed_at = None
                    profile.account_deletion_review_notes = ''
                    profile.save(update_fields=[
                        'account_deletion_requested_at',
                        'account_deletion_reason',
                        'account_deletion_request_status',
                        'account_deletion_reviewed_at',
                        'account_deletion_review_notes',
                    ])
                    messages.success(request, 'Your permanent deletion request has been submitted for admin review.')
                    return redirect('profile')
            else:
                messages.error(request, 'Please confirm your password to continue.')

    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = UserProfileUpdateForm(instance=profile)
        pass_form = PasswordChangeForm(request.user)

    return render(request, 'main/auth/profile.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'pass_form': pass_form,
        'deactivate_form': deactivate_form,
        'permanent_delete_form': permanent_delete_form,
    })


def reactivate_account(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ReactivateAccountForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data['user']
            reactivate_user_account(user)
            messages.success(request, 'Your account has been reactivated. You can log in now.')
            return redirect('login')
    else:
        form = ReactivateAccountForm()

    return render(request, 'main/auth/reactivate_account.html', {'form': form})


def send_verification_email(request, user, profile):
    current_site = get_current_site(request)
    mail_subject = "Activate your account."
    message = render_to_string('main/auth/acc_active_email.html', {
        'user': user,
        'domain': current_site.domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': profile.verification_token,
    })
    email = EmailMessage(mail_subject, message, to=[user.email])
    email.send()


def check_email(request):
    return render(request, 'main/auth/check_email.html')


def verify_email(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None:
        profile = UserProfile.objects.get(user=user)
        is_valid = (
            profile.verification_token == token
            and (timezone.now() - profile.token_created_at).total_seconds() < 3600
        )
        if is_valid:
            user.is_active = True
            user.save()
            profile.is_verified = True
            profile.verification_token = None
            profile.token_created_at = None
            profile.save()
            login(request, user)
            messages.success(request, 'Your account has been activated!')
            return redirect('dashboard')
        messages.error(request, 'Activation link is invalid or expired!')
    else:
        messages.error(request, 'Activation link is invalid!')

    return render(request, 'main/auth/verification_status.html')


def vendor_register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                with transaction.atomic():
                    user = form.save()
                    send_otp(email, user)
            except Exception:
                messages.error(request, 'We could not send your OTP right now. Please try again.')
                return render(request, 'main/auth/register.html', {
                    'form': form,
                    'registration_mode': 'vendor',
                })

            request.session['pending_email'] = email
            request.session['pending_user_id'] = user.id
            _mark_otp_sent(request.session)
            messages.success(
                request,
                f"An OTP has been sent to {email}. Please enter it to complete registration.",
            )
            return redirect('verify_otp')
    else:
        form = CustomUserCreationForm(initial={'role': 'vendor'})

    return render(request, 'main/auth/register.html', {
        'form': form,
        'registration_mode': 'vendor',
    })
