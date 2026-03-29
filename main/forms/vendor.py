from pathlib import Path

from django import forms
from django.forms import formset_factory

from ..models import Booking, BookingOperation, PackageDay, PackageDayOption, TripItem, TripItemAttachment


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
    description = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': "Describe the day's events..."}))
    inclusions = forms.CharField(max_length=255, required=False, help_text="Comma-separated items, e.g., Breakfast, Museum Tickets", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Breakfast, Museum Tickets'}))

    def clean_title(self):
        return self.cleaned_data['title'].strip()

    def clean_description(self):
        return self.cleaned_data['description'].strip()

    def clean_inclusions(self):
        return self.cleaned_data.get('inclusions', '').strip()


ItineraryFormSet = formset_factory(ItineraryDayForm, extra=1, can_delete=True)


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
        fields = ['package_day', 'option_type', 'title', 'description', 'additional_cost', 'is_required', 'sort_order', 'action_link']
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


class VendorCancellationReviewForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['vendor_committed_cost', 'vendor_cancellation_notes']
        widgets = {
            'vendor_committed_cost': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
            }),
            'vendor_cancellation_notes': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'rows': 2,
                'placeholder': 'Explain what has already been booked or paid',
            }),
        }

    def __init__(self, *args, booking=None, **kwargs):
        self.booking = booking or kwargs.get('instance')
        super().__init__(*args, **kwargs)

    def clean_vendor_committed_cost(self):
        committed_cost = self.cleaned_data['vendor_committed_cost']
        if committed_cost < 0:
            raise forms.ValidationError('Committed cost cannot be negative.')
        if self.booking and committed_cost > self.booking.total_price:
            raise forms.ValidationError('Committed cost cannot exceed the booking total.')
        return committed_cost

    def clean_vendor_cancellation_notes(self):
        return self.cleaned_data.get('vendor_cancellation_notes', '').strip()


class VendorBookingOperationsForm(forms.ModelForm):
    class Meta:
        model = BookingOperation
        fields = [
            'guide_name',
            'guide_contact',
            'jeep_driver_name',
            'jeep_plate_number',
            'hotel_name',
            'hotel_confirmation_code',
            'permit_status',
            'permit_reference',
            'operation_notes',
            'proof_document',
        ]
        widgets = {
            'guide_name': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Guide name'}),
            'guide_contact': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Guide phone'}),
            'jeep_driver_name': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Driver name'}),
            'jeep_plate_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Jeep plate no.'}),
            'hotel_name': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Hotel name'}),
            'hotel_confirmation_code': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Confirmation code'}),
            'permit_status': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'permit_reference': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Permit reference'}),
            'operation_notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2, 'placeholder': 'What has been arranged so far?'}),
            'proof_document': forms.ClearableFileInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in [
            'guide_name',
            'guide_contact',
            'jeep_driver_name',
            'jeep_plate_number',
            'hotel_name',
            'hotel_confirmation_code',
            'permit_reference',
            'operation_notes',
        ]:
            cleaned_data[field_name] = cleaned_data.get(field_name, '').strip()
        return cleaned_data


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
