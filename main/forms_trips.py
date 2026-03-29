from pathlib import Path

from django import forms

from .models import TripItem, TripItemAttachment


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
