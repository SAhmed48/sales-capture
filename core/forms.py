import phonenumbers
from django import forms
from django.core.exceptions import ValidationError

from .models import Submission


class SubmissionForm(forms.ModelForm):
    class Meta:
        model = Submission
        fields = ['name', 'phone', 'email', 'address', 'zip_code', 'country', 'city']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'John Doe',
                'autocomplete': 'name',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '+1 234 567 8900',
                'autocomplete': 'tel',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-input',
                'placeholder': 'john@example.com',
                'autocomplete': 'email',
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': '123 Main Street, Apt 4',
                'rows': 3,
                'autocomplete': 'street-address',
            }),
            'zip_code': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': '12345',
                'autocomplete': 'postal-code',
            }),
            'country': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'United States',
                'autocomplete': 'country-name',
            }),
            'city': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'New York',
                'autocomplete': 'address-level2',
            }),
        }

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if not phone:
            return phone
        try:
            parsed = phonenumbers.parse(phone, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValidationError('Please enter a valid phone number.')
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValidationError('Please enter a valid phone number.')
