from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm
from django.contrib.auth import authenticate
from .models import User


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Enter your email'}))
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Choose a username'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Create a password'}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Confirm password'}))
    student_id = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Enter your Student ID'}))
    department = forms.ChoiceField(choices=User.DEPARTMENTS, widget=forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Enter phone number'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'student_id', 'department', 'phone']


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Username or Email'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Enter your password'}))


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Enter your email'}))


class SetNewPasswordForm(SetPasswordForm):
    new_password1 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'New password'}))
    new_password2 = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'placeholder': 'Confirm new password'}))


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}))
    last_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'department', 'profile_picture', 'cover_photo', 'bio', 'address', 'student_id']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}),
            'department': forms.Select(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}),
            'profile_picture': forms.FileInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}),
            'cover_photo': forms.FileInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}),
            'bio': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'rows': 3}),
            'address': forms.Textarea(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition', 'rows': 2}),
        }


class UserSettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['email', 'phone']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}),
            'phone': forms.TextInput(attrs={'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'}),
        }
