from django import forms
from .models import Post, Category, CampusLocation


class PostForm(forms.ModelForm):
    title = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition',
        'placeholder': 'Enter post title'
    }))
    description = forms.CharField(widget=forms.Textarea(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition',
        'placeholder': 'Describe the item in detail...',
        'rows': 5
    }))
    category = forms.ModelChoiceField(queryset=Category.objects.all(), widget=forms.Select(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))
    location = forms.ModelChoiceField(queryset=CampusLocation.objects.all(), widget=forms.Select(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))
    post_type = forms.ChoiceField(choices=Post.POST_TYPES, widget=forms.Select(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))
    date_lost_found = forms.DateField(widget=forms.DateInput(attrs={
        'type': 'date',
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))
    contact_info = forms.CharField(required=False, widget=forms.Textarea(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition',
        'rows': 3,
        'placeholder': 'Phone, email, or other contact details'
    }))
    reward_amount = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition',
        'placeholder': 'Reward amount (optional)'
    }))
    image = forms.ImageField(required=False, widget=forms.FileInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError('Image file too large (max 5MB)')
            from PIL import Image
            try:
                img = Image.open(image)
                img.verify()
                valid = ['jpeg', 'png', 'gif', 'webp']
                if img.format and img.format.lower() not in valid:
                    raise forms.ValidationError('Unsupported image format. Use JPEG, PNG, GIF or WebP.')
            except Exception:
                raise forms.ValidationError('Invalid or corrupted image file.')
        return image

    class Meta:
        model = Post
        fields = ['title', 'description', 'category', 'location', 'post_type', 'date_lost_found', 'image', 'contact_info', 'reward_amount']
