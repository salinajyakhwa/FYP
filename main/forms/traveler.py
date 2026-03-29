from decimal import Decimal

from django import forms

from ..models import Booking, BookingDispute


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
