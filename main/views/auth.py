from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
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
    UserProfileUpdateForm,
    UserUpdateForm,
)
from ..models import EmailOTP, UserProfile
from ..services.accounts import anonymize_user_account
from ..utils import send_otp

User = get_user_model()


class CustomLoginView(auth_views.LoginView):
    template_name = 'main/auth/login.html'
    authentication_form = CustomAuthenticationForm


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            email = form.cleaned_data['email']

            send_otp(email, user)

            request.session['pending_email'] = email
            request.session['pending_user_id'] = user.id
            messages.success(
                request,
                f"An OTP has been sent to {email}. Please enter it to complete registration.",
            )
            return redirect('verify_otp')
    else:
        form = CustomUserCreationForm()
    return render(request, 'main/auth/register.html', {'form': form})


def verify_otp(request):
    pending_email = request.session.get('pending_email')
    pending_user_id = request.session.get('pending_user_id')

    if not pending_email or not pending_user_id:
        messages.info(request, 'Start registration first to verify your email.')
        return redirect('register')

    if request.method == 'POST':
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

        return render(request, 'main/auth/verify_otp.html', {
            'email': pending_email,
            'error': 'Invalid or expired OTP. Please try again.',
        })

    return render(request, 'main/auth/verify_otp.html', {'email': pending_email})


@login_required
def profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    deletion_form = AccountDeletionRequestForm(user=request.user)

    if request.method == 'POST':
        if 'update_profile' in request.POST:
            user_form = UserUpdateForm(request.POST, instance=request.user)
            profile_form = UserProfileUpdateForm(request.POST, request.FILES, instance=profile)
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
            deletion_form = AccountDeletionRequestForm(user=request.user)

        elif 'delete_account' in request.POST:
            user_form = UserUpdateForm(instance=request.user)
            profile_form = UserProfileUpdateForm(instance=profile)
            pass_form = PasswordChangeForm(request.user)
            deletion_form = AccountDeletionRequestForm(request.POST, user=request.user)
            if deletion_form.is_valid():
                reason = deletion_form.cleaned_data['reason']

                if profile.role == 'vendor':
                    vendor = getattr(profile, 'vendor', None)
                    if not vendor:
                        messages.error(request, 'Vendor profile is incomplete.')
                    elif vendor.deletion_request_status == 'pending':
                        messages.info(request, 'Your vendor account deletion request is already pending admin review.')
                    else:
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
                        messages.success(request, 'Your vendor account deletion request has been submitted for admin review.')
                        return redirect('profile')
                else:
                    profile.account_deletion_requested_at = timezone.now()
                    profile.account_deletion_reason = reason
                    profile.save(update_fields=['account_deletion_requested_at', 'account_deletion_reason'])
                    anonymize_user_account(request.user)
                    logout(request)
                    messages.success(request, 'Your account has been deactivated successfully.')
                    return redirect('home')
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
        'deletion_form': deletion_form,
    })


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
            user = form.save()
            email = form.cleaned_data['email']

            send_otp(email, user)

            request.session['pending_email'] = email
            request.session['pending_user_id'] = user.id
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
