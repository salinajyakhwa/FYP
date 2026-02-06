from django import forms
from django.forms import formset_factory
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserChangeForm, PasswordChangeForm, UserCreationForm

import uuid
from django.utils import timezone

from .models import Review, TravelPackage, UserProfile, Vendor

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

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, initial='traveler', widget=forms.RadioSelect)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email', 'role',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.is_active = False # Deactivate user until email is verified
        if commit:
            user.save()
            role = self.cleaned_data.get('role')
            profile, created = UserProfile.objects.get_or_create(
                user=user,
                defaults={'role': role},
            )
            # Generate verification token
            profile.verification_token = uuid.uuid4().hex
            profile.token_created_at = timezone.now()
            profile.save(update_fields=['role', 'verification_token', 'token_created_at'])

            if not created and profile.role != role:
                profile.role = role
                profile.save(update_fields=['role'])
            if role == 'vendor':
                Vendor.objects.get_or_create(
                    user_profile=profile,
                    defaults={'name': user.username, 'description': ''},
                )
        return user

class ItineraryDayForm(forms.Form):
    day = forms.IntegerField(widget=forms.NumberInput(attrs={'class': 'form-control'}))
    title = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    description = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

ItineraryFormSet = formset_factory(ItineraryDayForm, extra=1, can_delete=True)

class TravelPackageForm(forms.ModelForm):
    class Meta:
        model = TravelPackage
        fields = ['name', 'description', 'image', 'price', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
