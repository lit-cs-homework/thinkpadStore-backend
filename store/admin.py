import os
import io, csv
from django.contrib import admin
from .models import User, Product, Cart, DiscountPromotion
from .models import CartItem
from django import forms
from django.forms.widgets import ClearableFileInput, FileInput
from django.utils.safestring import mark_safe
from django.core.files.storage import default_storage

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    search_fields = ['email', 'username']  # Enable search by email and username

class ClearableMultiFileInput(ClearableFileInput):
    allow_multiple_selected = True



class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", ClearableMultiFileInput(attrs={'multiple': True}))
        super().__init__(*args, **kwargs)
    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class EquipmentCSVWidget(forms.Textarea):
    """Simple multiline textarea for CSV input (no header). Each line: name,extra_price"""
    pass

class ProductAdminForm(forms.ModelForm):
    new_images = MultipleFileField(
        required=False,
        label='Upload additional images',
        help_text='Select one or more files to upload.'
    )
    existing_images = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Delete existing images',
        help_text='Select images to delete.'
    )
    equipments_csv = forms.CharField(
        required=False,
        widget=EquipmentCSVWidget(attrs={'rows': 6}),
        label='equipements',
        help_text='Each line: name,extra_price (CSV without header)'
    )

    class Meta:
        model = Product
        exclude = ['images', 'images_max_ord', 'equipments']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            images = self.instance.list_images()
            # Use path as value, filename as label
            self.fields['existing_images'].choices = [
                (img, os.path.basename(img)) for img in images
            ]
            # populate equipments_csv with current equipments
            eqs = self.instance.equipments
            lines = []
            for e in eqs:
                name = e['name']
                extra_price = e['extra_price']
                # ensure commas in values are preserved minimally by not altering
                lines.append(f"{name},{extra_price}")
            self.fields['equipments_csv'].initial = '\n'.join(lines)
        else:
            self.fields['existing_images'].choices = []
            self.fields['equipments_csv'].initial = ''

    def clean_equipments_csv(self):
        eq_csv = self.cleaned_data.get('equipments_csv', '')
        f = io.StringIO(eq_csv)
        reader = csv.reader(f)
        normalized = []
        for index, row in enumerate(reader):
            if not row:
                continue
            if len(row) != 2:
                raise forms.ValidationError(f'bad line {index + 1}: ' "Each equipment line must have exactly two values: name and extra_price.")
            name = row[0].strip()
            s_price = row[1].strip()
            try:
                _ = float(s_price)
            except ValueError:
                raise forms.ValidationError(f'bad line {index + 1}: "Price must be a valid number."')
            normalized.append({'name': name, 'extra_price': s_price})
        return normalized
    
    def clean(self):
        obj = self.instance
        obj.equipments = self.cleaned_data.get('equipments_csv')
        #obj.save(update_fields=['equipments'])
        return super().clean()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    search_fields = ['name', 'model']  # Enable search by name and model
    list_filter = ('model',)
    readonly_fields = ('image_preview',)

    def _render_image_block(self, url, label):
        """Render a single image preview block as HTML."""
        return f"""
            <div style="text-align: center; border: 1px solid #ddd; padding: 5px;">
            <img src="{url}" style="max-height: 150px; max-width: 150px; object-fit: contain;" /><br>
            <small>{label}</small>
            </div>
        """

    def image_preview(self, obj):
        if not obj:
            return ''
        html = '<div style="display: flex; flex-wrap: wrap; gap: 10px;">'
        
        # Primary image
        if obj.image:
            html += self._render_image_block(obj.image.url, 'Primary')
        
        # Additional images
        for img_path in obj.list_images():
            url = default_storage.url(img_path)
            html += self._render_image_block(url, os.path.basename(img_path))
        
        html += '</div>'
        return mark_safe(html)
    
    image_preview.short_description = 'Image Previews'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Handle deletions
        to_delete = form.cleaned_data.get('existing_images', [])
        obj.remove_images(to_delete)

        # Handle uploads
        obj.add_images(request.FILES.getlist('new_images'))

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0

class CartAdmin(admin.ModelAdmin):
    inlines = [CartItemInline]
    search_fields = ['user__username', 'user__email']  # Enable search by user's username and email

@admin.register(DiscountPromotion)
class PromotionAdmin(admin.ModelAdmin):
    search_fields = ['name']

    #list_display = ('name', 'start_date', 'end_date', 'discount')
    list_filter = ('start_date', 'end_date')

admin.site.register(Cart, CartAdmin)
