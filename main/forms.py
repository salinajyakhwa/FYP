from django import forms
from django.forms import formset_factory
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserChangeForm, PasswordChangeForm, UserCreationForm

from .models import Review, TravelPackage, UserProfile

class UserUpdateForm(UserChangeForm):
    password = None # Remove the password field from this form
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

# New custom form for user registration with role selection
class CustomUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, initial='traveler', widget=forms.RadioSelect)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('role',)

    # Override save method to create UserProfile
    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            role = self.cleaned_data.get('role')
            UserProfile.objects.create(user=user, role=role)
        return user

class ItineraryDayForm(forms.Form):
    day = forms.IntegerField(widget=forms.NumberInput(attrs={'class': 'form-control'}))
    title = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'class': 'form-control'}))
    description = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

ItineraryFormSet = formset_factory(ItineraryDayForm, extra=1, can_delete=True)

# class TravelPackageForm(forms.ModelForm):
#     class Meta:
#         model = TravelPackage
#         fields = ['name', 'description', 'price', 'start_date', 'end_date']
#         widgets = {
#             'name': forms.TextInput(attrs={'class': 'form-control'}),
#             'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
#             'price': forms.NumberInput(attrs={'class': 'form-control'}),
#             'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
#             'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
#         }

class TravelPackageForm(forms.ModelForm):
    class Meta:
        model = TravelPackage
        fields = ['name', 'description', 'location', 'hotel_info', 'travel_type', 'price', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Paris, France'}),
            'hotel_info': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'e.g., 5-star hotel, breakfast included'}),
            'travel_type': forms.Select(attrs={'class': 'form-select'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
