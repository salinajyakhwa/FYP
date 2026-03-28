from django import forms
from django.forms import formset_factory
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, PasswordChangeForm, UserCreationForm
from decimal import Decimal
from pathlib import Path

import uuid
from django.utils import timezone

from .models import (
    Review,
    TravelPackage,
    UserProfile,
    Vendor,
    PackageDay,
    PackageDayOption,
    TripItem,
    TripItemAttachment,
    ChatMessage,
)

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
                vendor, _ = Vendor.objects.get_or_create(
                    user_profile=profile,
                    defaults={
                        'name': user.username,
                        'description': '',
                    },
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


class BookingTravelerForm(forms.Form):
    adult_count = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        label='Adults',
    )
    child_count = forms.IntegerField(
        min_value=0,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        label='Children',
    )

    def total_travelers(self):
        if not hasattr(self, 'cleaned_data'):
            return 1
        return self.cleaned_data['adult_count'] + self.cleaned_data['child_count']

    def calculate_total(self, adult_unit_price, child_unit_price):
        adult_total = Decimal(self.cleaned_data['adult_count']) * Decimal(adult_unit_price)
        child_total = Decimal(self.cleaned_data['child_count']) * Decimal(child_unit_price)
        return adult_total + child_total

class ItineraryDayForm(forms.Form):
    ACTIVITY_CHOICES = [
        ('tour', 'Tour'),
        ('meal', 'Meal'),
        ('free_time', 'Free Time'),
        ('accommodation', 'Accommodation'),
        ('travel', 'Travel'),
    ]
    day = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Day'})
    )
    title = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Activity Title'}))
    activity_type = forms.ChoiceField(choices=ACTIVITY_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    description = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Describe the day\'s events...'}))
    inclusions = forms.CharField(max_length=255, required=False, help_text="Comma-separated items, e.g., Breakfast, Museum Tickets", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Breakfast, Museum Tickets'}))

    def clean_title(self):
        return self.cleaned_data['title'].strip()

    def clean_description(self):
        return self.cleaned_data['description'].strip()

    def clean_inclusions(self):
        return self.cleaned_data.get('inclusions', '').strip()

ItineraryFormSet = formset_factory(ItineraryDayForm, extra=1, can_delete=True)

class TravelPackageForm(forms.ModelForm):
    class Meta:
        model = TravelPackage
        fields = ['name', 'description', 'location', 'travel_type', 'image', 'price', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'travel_type': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class PackageDayForm(forms.ModelForm):
    class Meta:
        model = PackageDay
        fields = ['day_number', 'title', 'description', 'sort_order']
        widgets = {
            'day_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }

    def __init__(self, *args, package=None, **kwargs):
        self.package = package
        super().__init__(*args, **kwargs)

    def clean_title(self):
        return self.cleaned_data['title'].strip()

    def clean_description(self):
        return self.cleaned_data['description'].strip()

    def clean(self):
        cleaned_data = super().clean()
        day_number = cleaned_data.get('day_number')

        if self.package and day_number:
            qs = PackageDay.objects.filter(package=self.package, day_number=day_number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('day_number', 'This package already has an itinerary entry for that day.')

        return cleaned_data


class PackageDayOptionForm(forms.ModelForm):
    class Meta:
        model = PackageDayOption
        fields = ['package_day', 'option_type', 'title', 'description', 'additional_cost', 'is_required', 'sort_order','action_link']
        widgets = {
            'package_day': forms.Select(attrs={'class': 'form-select'}),
            'option_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'additional_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'action_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Optional booking link'}),
        }

    def __init__(self, *args, package=None, **kwargs):
        self.package = package
        super().__init__(*args, **kwargs)
        if self.package:
            self.fields['package_day'].queryset = PackageDay.objects.filter(package=self.package).order_by('day_number', 'sort_order', 'id')

    def clean_title(self):
        return self.cleaned_data['title'].strip()

    def clean_description(self):
        return self.cleaned_data['description'].strip()

    def clean_package_day(self):
        package_day = self.cleaned_data['package_day']
        if self.package and package_day.package_id != self.package.id:
            raise forms.ValidationError('Selected day does not belong to this package.')
        return package_day


class CustomItinerarySelectionForm(forms.Form):
    def __init__(self, *args, package=None, **kwargs):
        self.package = package
        super().__init__(*args, **kwargs)
        self.package_days = []
        self.option_map = {}

        if not self.package:
            return

        package_days = self.package.package_days.prefetch_related('options').all()
        for package_day in package_days:
            options = list(package_day.options.all())
            if not options:
                continue

            field_name = f'day_{package_day.id}'
            self.package_days.append(package_day)
            self.option_map[package_day.id] = {str(option.id): option for option in options}
            self.fields[field_name] = forms.ChoiceField(
                label=f'Day {package_day.day_number}: {package_day.title}',
                required=any(option.is_required for option in options),
                choices=[
                    (
                        str(option.id),
                        f"{option.title} ({option.get_option_type_display()}) (+Rs. {option.additional_cost})",
                    )
                    for option in options
                ],
                widget=forms.RadioSelect,
            )

    def clean(self):
        cleaned_data = super().clean()

        for package_day in self.package_days:
            field_name = f'day_{package_day.id}'
            selected_option_id = cleaned_data.get(field_name)
            if not selected_option_id:
                continue
            if selected_option_id not in self.option_map.get(package_day.id, {}):
                self.add_error(field_name, 'Selected option does not belong to this package day.')

        return cleaned_data

    def get_selected_options(self):
        selected_options = []

        for package_day in self.package_days:
            field_name = f'day_{package_day.id}'
            selected_option_id = self.cleaned_data.get(field_name)
            if not selected_option_id:
                continue
            selected_option = self.option_map[package_day.id][selected_option_id]
            selected_options.append((package_day, selected_option))

        return selected_options

    def calculate_total(self, base_price):
        total = Decimal(base_price)
        for _, selected_option in self.get_selected_options():
            total += selected_option.additional_cost
        return total


class TripItemVendorNotesForm(forms.ModelForm):
    class Meta:
        model = TripItem
        fields = ['vendor_notes']
        widgets = {
            'vendor_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Add operational notes for this trip item'}),
        }

    def clean_vendor_notes(self):
        return self.cleaned_data.get('vendor_notes', '').strip()


class TripItemAttachmentForm(forms.ModelForm):
    MAX_FILE_SIZE = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png'}

    class Meta:
        model = TripItemAttachment
        fields = ['title', 'attachment_type', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Attachment title'}),
            'attachment_type': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def clean_title(self):
        return self.cleaned_data['title'].strip()

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        suffix = Path(uploaded_file.name).suffix.lower()

        if suffix not in self.ALLOWED_EXTENSIONS:
            raise forms.ValidationError('Unsupported file type. Allowed types: PDF, JPG, JPEG, PNG.')

        if uploaded_file.size > self.MAX_FILE_SIZE:
            raise forms.ValidationError('File size must be 10 MB or less.')

        return uploaded_file


class ChatMessageForm(forms.ModelForm):
    class Meta:
        model = ChatMessage
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Type your message...',
            }),
        }

    def clean_message(self):
        message = self.cleaned_data['message'].strip()
        if not message:
            raise forms.ValidationError('Message cannot be empty.')
        return message
