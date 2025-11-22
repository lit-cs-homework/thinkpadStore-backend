from django.contrib import admin
from .models import User, Product, Cart, DiscountPromotion
from .models import CartItem

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    search_fields = ['email', 'username']  # Enable search by email and username

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    search_fields = ['name', 'model']  # Enable search by name and model
    list_filter = ('model',)


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
