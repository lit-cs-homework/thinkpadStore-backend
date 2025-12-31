from django.apps import AppConfig


class StoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'store'

    def ready(self):
        from .models import deleted_product_image_url as deleted_image_url
        # Ensure the deleted product image exists (best-effort; do not crash startup)
        try:
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage

            if not default_storage.exists(deleted_image_url):
                default_storage.save(
                    deleted_image_url,
                    ContentFile(
                        b"""<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="100" height="100" rx="8" ry="8" fill="#dc3545" />
  <text x="50" y="50" font-size="12" font-weight="600" fill="white" text-anchor="middle" dominant-baseline="middle">
    &#x1F5D1;&#xFE0F; Deleted Product
  </text>
</svg>"""
                    ),
                )
        except Exception:
            pass
        return super().ready()
