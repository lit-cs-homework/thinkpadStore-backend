"""
URL configuration for thinkpad_store project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from store.views import UserView, LoginView, ProductViewSet, CartViewSet, product_images_url
from store.assistant import AssistantChatView

DOC_CACHE_TIMEOUT = 0 # 60 * 60  # 1 hour
schema_view = get_schema_view(
   openapi.Info(
      title="API Documentation",
      default_version='v1',
      description="API documentation for your project",
      #contact=openapi.Contact(email="contact@example.com"),
      license=openapi.License(name="MIT License"),
   ),
   public=True,
   permission_classes=(permissions.AllowAny,),  # XXX: this proj is public (learning purpose)
)

router = DefaultRouter()
router.register('product', ProductViewSet, basename='product')
router.register('cart', CartViewSet, basename='cart')
router.register('user', UserView, basename='user')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', LoginView.as_view(), name='login'),
    path('login/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('assistant/chat/', AssistantChatView.as_view(), name='assistant_chat'),
    path('', include(router.urls)),
] + [
    # drf-yasg auto-generate OpenAPI JSON and UI
    path('swagger.yaml', schema_view.without_ui(cache_timeout=DOC_CACHE_TIMEOUT), name='schema-yaml'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=DOC_CACHE_TIMEOUT), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=DOC_CACHE_TIMEOUT), name='schema-redoc'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

