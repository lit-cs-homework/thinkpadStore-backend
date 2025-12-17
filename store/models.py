import os
from datetime import datetime, timezone
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models, transaction
from django.utils.text import slugify
from django.core.files.storage import default_storage


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
deleted_product_image_url = product_images_url + 'deleted_product_na.svg'

def product_image_upload_path(instance, filename):
    """
    Generate a unique file path for the product image based on the product's name and model.
    This will always append an index into the filename to avoid collisions and make
    it easy to track image ordering.
    """
    # delegate to the filename helper which can compute the index when needed
    return product_image_filename(instance, filename, index=None)


def product_image_filename(instance, filename, index=None):
    """Build the filename for a product image and ensure an index is appended.

    If index is not None, append it to the filename.
    """
    _, file_extension = os.path.splitext(filename)
    # Use slugify to create a safe filename
    safe_name = slugify(instance.get_unique_identifier())
    # derive index if not provided
    if index is None:
        #current_images = len(list(current_images)) + 1
        pass
    else:
        safe_name += '_' + str(index)
    return product_images_url + f"{safe_name}{file_extension}"

class ProductManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(**Product._DELETED_ONES_UNIQUE_ATTRS)

class Product(models.Model):
    name = models.CharField(max_length=255)
    model = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField()
    stock = models.PositiveIntegerField()
    image = models.FileField(upload_to=product_image_upload_path)
    images = models.JSONField(default=list)
    images_max_ord = models.PositiveIntegerField(default=0)
    equipments = models.JSONField(default=list, verbose_name='配置')

    

    # ensure the deleted placeholder is not in normal queries
    _objects_ = models.Manager()  # The default manager.
    @classmethod
    def exists_deleted_placeholder(cls):
        return cls._objects_.filter(**cls._DELETED_ONES_UNIQUE_ATTRS).exists()
    objects = ProductManager()

    class Meta:
        unique_together = ('name', 'model')

    def __str__(self):
        return self.name

    def get_unique_identifier(self):
        return f"{self.name}_{self.model}"

    def add_images(self, uploaded_files):
        """Save an uploaded file to storage using the same upload path logic and
        append the stored path to the images list.
        uploaded_file should be an UploadedFile or file-like object with a .name attribute.
        Returns the stored path (name) of the saved file.
        """
        # compute the next index explicitly so filenames are sequential
        imgs = self.images
        # XXX: the logic below is simple:
        #  for [1, 2, 4], cur_ord is still 4
        #   this works because default_storage.save will auto rename,
        #   by adding suffix consisted of random alpha
        cur_ord = self.images_max_ord + 1
        for cur_ord, uploaded_file in enumerate(uploaded_files, start=cur_ord):
            filename = product_image_filename(self, uploaded_file.name, index=cur_ord)
            saved_name = default_storage.save(filename, uploaded_file)
            imgs.append(saved_name)
        self.images_max_ord = cur_ord
        self.save(update_fields=['images', 'images_max_ord'])

    def remove_images(self, paths):
        """Remove an image path from this product and delete the file from storage."""
        imgs = self.images
        hi = self.images_max_ord - 1
        for path in paths:
            if path not in imgs: continue
            default_storage.delete(path)
            i = imgs.index(path)
            del imgs[i]
            #imgs.remove(path)
            if i == hi:
                hi -= 1
        self.images_max_ord = hi + 1
        self.save(update_fields=['images', 'images_max_ord'])

    def list_images(self):
        """Return the list of stored image paths for this product."""
        return self.images

    # Equipments helpers
    def list_equipments(self):
        """Return the list of equipments. Each item is a dict with 'name' and 'price'."""
        return self.equipments or []

    def add_equipment(self, name: str, price):
        eqs = self.list_equipments()
        eqs.append({'name': name, 'price': str(price)})
        self.equipments = eqs
        self.save(update_fields=['equipments'])

    def remove_equipment_by_name(self, name: str):
        eqs = [e for e in self.list_equipments() if e.get('name') != name]
        self.equipments = eqs
        self.save(update_fields=['equipments'])

    def equipments_total_price(self):
        total = 0
        for e in self.list_equipments():
            try:
                total += float(e.get('price', 0))
            except Exception:
                pass
        return total

    _DELETED_ONES_UNIQUE_ATTRS = dict(
        name="(Deleted Product)",
        model="N/A",
    )
    _DELETED_ONES_ATTRS = dict(**_DELETED_ONES_UNIQUE_ATTRS,
        price=0.0, stock=0,
        description="This kind was deleted by provider.",
        image=deleted_product_image_url,
        equipments=[],
    )
    @classmethod
    def get_placeholder_for_deleted(cls):
        return cls.objects.get_or_create(**cls._DELETED_ONES_UNIQUE_ATTRS)[0]

    # Override the delete method to remove the image file
    def delete(self, *args, **kwargs):
        # delete primary image file
        self.image.delete(save=False) # if `save` this line, recsursive loop
        # delete additional images stored as paths
        for img_path in list(self.images):
            try:
                default_storage.delete(img_path)
            except Exception:
                # best-effort deletion
                pass
        # this will also `save`
        super().delete(*args, **kwargs)

        with transaction.atomic():
            CartItem.handle_product_deletion(self)

    # no need to override the save method to delete the old image file when updating
    #  as with `product_image_upload_path` and `unique_together`,
    #  the old image file will be overwritten


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
    quantity = models.PositiveIntegerField(default=1)

    @classmethod
    def handle_product_deletion(cls, product):
        """
        Handle the deletion of a product by replacing it with a 'Deleted Product' placeholder
        in all cart items that reference the deleted product.
        """
        deleted_product = Product.get_placeholder_for_deleted()
        affected_items = cls.objects.filter(product=product)
        for item in affected_items:
            item.product = deleted_product
            item.save(update_fields=['product'])

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
