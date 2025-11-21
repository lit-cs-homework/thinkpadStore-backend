import os
from datetime import datetime, timezone
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

# 用户模型
class User(AbstractUser):
    email = models.EmailField(unique=True)
    is_vip = models.BooleanField(default=False)

product_images_url = 'product_images/'

# 商品模型
class Product(models.Model):
    name = models.CharField(max_length=255)
    model = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    stock = models.PositiveIntegerField()
    image = models.FileField(upload_to=product_images_url)

    def __str__(self):
        return self.name
    

    @staticmethod
    def _try_purge_image_file(image):
        if image:
            # Delete the image file from the filesystem
            image_path = os.path.join(settings.MEDIA_ROOT, image.name)
            if os.path.isfile(image_path):
                os.remove(image_path)
    # Override the delete method to remove the image file
    def delete(self, *args, **kwargs):
        Product._try_purge_image_file(self.image)
        super().delete(*args, **kwargs)

    # Override the save method to delete the old image file when updating
    def save(self, *args, **kwargs):
        if self.pk:  # Check if the object already exists in the database
            old_product = Product.objects.filter(pk=self.pk).first()
            if old_product is not None and old_product.image != self.image:
                Product._try_purge_image_file(old_product.image)
        super().save(*args, **kwargs)


# 购物车模型
class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def total_price(self):
        return sum(item.total_price() for item in
            CartItem.objects.filter(cart=self)
        )

    def __str__(self):
        return f"Cart of {self.user.username}"

# 购物车项模型
class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='cart_items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def original_total_price(self):
        return self.quantity * self.product.price

    def total_price(self):
        now = datetime.now() #TODO: check if timezone is correct
        dis = DiscountPromotion.objects.filter(
            start_date__gte=now,
            end_date__lte=now,
        )
        res = self.original_total_price()
        if dis is not None:
            for d in dis:
                res = res * d.rate()
        return res

    def __str__(self):
        return f"{self.quantity} x {self.product.name} in {self.cart.user.username}'s cart"


class Promotion(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()

class DiscountPromotion(Promotion):
    '打折; discount 8 表示八折'
    discount = models.SmallIntegerField()
    def rate(self):
        return 1.0 - self.discount / 10.0
