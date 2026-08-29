from django import forms
from .models import Post, Category, CampusLocation
from apps.accounts.validators import validate_post_image


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
    location_name = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition',
        'placeholder': 'e.g. Building 3, 2nd Floor, Room 201',
    }), help_text='Type the location manually (e.g. Building 3, Room 201)')
    post_type = forms.ChoiceField(choices=Post.POST_TYPES, widget=forms.Select(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))
    date_lost_found = forms.DateField(widget=forms.DateInput(attrs={
        'type': 'date',
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))
    contact_info = forms.CharField(widget=forms.Textarea(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition',
        'rows': 3,
        'placeholder': 'Phone, email, or other contact details'
    }))
    image = forms.ImageField(required=False, widget=forms.FileInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition'
    }))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contact_info'].required = True
        if self.instance and self.instance.pk:
            self.fields['location_name'].initial = self.instance.location_name

    def clean_image(self):
        image = self.cleaned_data.get('image')
        post_type = self.data.get('post_type', '')
        if post_type == 'found' and not image:
            raise forms.ValidationError('An image is required for found item posts.')
        if image:
            validate_post_image(image)
        return image

    def clean_title(self):
        title = self.cleaned_data.get('title', '')
        if len(title.strip()) < 5:
            raise forms.ValidationError('Title must be at least 5 characters long.')
        return title.strip()

    def clean_description(self):
        desc = self.cleaned_data.get('description', '')
        if len(desc.strip()) < 10:
            raise forms.ValidationError('Description must be at least 10 characters long.')
        return desc.strip()

    def clean_location_name(self):
        name = self.cleaned_data.get('location_name', '').strip()
        if not name:
            raise forms.ValidationError('Location is required.')
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        location_name = self.cleaned_data.get('location_name', '').strip()
        if location_name:
            location_obj, _ = CampusLocation.objects.get_or_create(
                name=location_name,
                defaults={'slug': location_name.lower().replace(' ', '-').replace(',', '')[:100]},
            )
            instance.location = location_obj
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Post
        fields = ['title', 'description', 'category', 'post_type', 'date_lost_found', 'image', 'contact_info']
