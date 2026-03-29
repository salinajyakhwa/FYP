import uuid

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import UserProfile, Vendor


class UserProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bio', 'profile_picture']
        widgets = {
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'profile_picture': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }


class UserUpdateForm(UserChangeForm):
    password = None

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, initial='traveler', widget=forms.RadioSelect)
    pan_card_photo = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))
    id_document_type = forms.ChoiceField(
        required=False,
        choices=[('', 'Select ID Type')] + list(Vendor.ID_DOCUMENT_TYPE_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    id_document_photo = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email', 'role',)

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')

        if role == 'vendor':
            if not cleaned_data.get('pan_card_photo'):
                self.add_error('pan_card_photo', 'PAN card upload is required for vendor registration.')
            if not cleaned_data.get('id_document_type'):
                self.add_error('id_document_type', 'Select a valid ID document type.')
            if not cleaned_data.get('id_document_photo'):
                self.add_error('id_document_photo', 'ID document upload is required for vendor registration.')

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.is_active = False
        if commit:
            user.save()
            role = self.cleaned_data.get('role')
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': role},
            )
            profile.verification_token = uuid.uuid4().hex
            profile.token_created_at = timezone.now()
            profile.save(update_fields=['role', 'verification_token', 'token_created_at'])

            if not created and profile.role != role:
                profile.role = role
                profile.save(update_fields=['role'])
            if role == 'vendor':
                vendor, _ = Vendor.objects.get_or_create(
                    user_profile=profile,
                    defaults={'name': user.username, 'description': ''},
                )
                vendor.name = user.username
                vendor.description = vendor.description or ''
                vendor.pan_card_photo = self.cleaned_data['pan_card_photo']
                vendor.id_document_type = self.cleaned_data['id_document_type']
                vendor.id_document_photo = self.cleaned_data['id_document_photo']
                vendor.status = 'pending'
                vendor.save()
        return user


class CustomAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)

        profile = getattr(user, 'userprofile', None)
        if not profile or profile.role != 'vendor':
            return

        vendor = getattr(profile, 'vendor', None)
        if not vendor:
            raise forms.ValidationError(
                'Your vendor profile is incomplete. Please contact an administrator.',
                code='inactive',
            )

        if vendor.status == 'pending':
            raise forms.ValidationError(
                'Your vendor registration is pending admin approval.',
                code='inactive',
            )

        if vendor.status == 'rejected':
            raise forms.ValidationError(
                'Your vendor registration was rejected. Please contact the administrator.',
                code='inactive',
            )
