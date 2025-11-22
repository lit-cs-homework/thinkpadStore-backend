import os
from datetime import datetime, timezone
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True)
    is_vip = models.BooleanField(default=False)
    def save(self, *args, **kwargs):
        is_new = not self.pk
        res = super().save(*args, **kwargs)
        if is_new:
            # if new user
            Cart.objects.create(user=self)
        return res
    # no need to override delete(), as CASCADING will handle Cart deletion

product_images_url = 'product_images/'


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


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    def total_price(self):
        return sum(item.total_price() for item in
            CartItem.objects.filter(cart=self)
        )

    def __str__(self):
        return f"Cart of {self.user.username}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='cart_items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    #TODO: on_delete behavior: when product is deleted, replace with a "deleted product" placeholder?
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
    
    def save(self, *args, **kwargs):
        """
        Custom save method.
        If this is a new object and a similar one already exists,
        increment the existing one instead of creating a new one.
        """
        ## Check if this is a new object (has no primary key yet)
        if not self.pk: #_state.adding:
            # Try to find an existing cart item for this user and product
            existing_item = CartItem.objects.filter(
                cart=self.cart,
                product=self.product
            ).first()

            if existing_item:
                # If it exists, increment its quantity and save it
                existing_item.quantity += self.quantity
                existing_item.save(update_fields=['quantity'])
                # make sure response is correct
                #TODO: get rid of hand-writing
                self.id = existing_item.id
                self.quantity = existing_item.quantity  
                # Prevent saving the new object `self`
                return
        # If it's not a new object or no duplicate was found, save as usual
        super().save(*args, **kwargs)
    # no need to override delete()

class Promotion(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()

class DiscountPromotion(Promotion):
    'discount 8 means 20% off, i.e., pay 80%'
    discount = models.SmallIntegerField()
    def rate(self):
        return 1.0 - self.discount / 10.0
