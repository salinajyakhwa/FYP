from decimal import Decimal

from django import forms

from .models import Booking, BookingDispute, BookingOperation


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


class BookingCancellationRequestForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['cancellation_reason']
        widgets = {
            'cancellation_reason': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'rows': 2,
                'placeholder': 'Reason for cancellation',
            }),
        }

    def clean_cancellation_reason(self):
        return self.cleaned_data['cancellation_reason'].strip()


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


class BookingDisputeForm(forms.ModelForm):
    class Meta:
        model = BookingDispute
        fields = ['subject', 'message']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': 'form-control form-control-sm',
                'placeholder': 'Issue title',
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control form-control-sm',
                'rows': 3,
                'placeholder': 'Explain the issue clearly',
            }),
        }

    def clean_subject(self):
        return self.cleaned_data['subject'].strip()

    def clean_message(self):
        return self.cleaned_data['message'].strip()
