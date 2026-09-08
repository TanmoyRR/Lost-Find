from django import forms
from io import BytesIO
from PIL import Image as PILImage
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
    recovery_token = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-3 rounded-xl border border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 outline-none transition font-mono tracking-widest uppercase',
        'placeholder': 'LF-XXXXXX',
        'maxlength': 10,
    }), help_text='Optional. If you have a recovery token from the owner, enter it here to link your found post to their lost post.')

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

    def _compress_image(self, image):
        try:
            img = PILImage.open(image)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            max_size = (1200, 1200)
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, PILImage.LANCZOS)
            buf = BytesIO()
            img.save(buf, format='JPEG', quality=80, optimize=True)
            buf.seek(0)
            from django.core.files.uploadedfile import InMemoryUploadedFile
            return InMemoryUploadedFile(
                buf, 'image', f'{image.name.rsplit(".", 1)[0]}.jpg',
                'image/jpeg', buf.getbuffer().nbytes, None,
            )
        except Exception:
            return image

    def save(self, commit=True):
        instance = super().save(commit=False)
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'file'):
            instance.image = self._compress_image(image)
        location_name = self.cleaned_data.get('location_name', '').strip()
        if location_name:
            slug = location_name.lower().replace(' ', '-').replace(',', '').strip()[:100]
            location_obj, _ = CampusLocation.objects.get_or_create(
                slug=slug,
                defaults={'name': location_name, 'slug': slug},
            )
            instance.location = location_obj
        if commit:
            instance.save()
        return instance

    class Meta:
        model = Post
        fields = ['title', 'description', 'category', 'post_type', 'date_lost_found', 'image', 'contact_info']
