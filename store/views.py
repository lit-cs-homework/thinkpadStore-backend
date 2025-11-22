from django.conf import settings
#from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, exceptions
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import User, Product, CartItem, Cart, product_images_url
from .serializers import UserSerializer, ProductSerializer, CartItemSerializer
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

# 用户注册
class UserView(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    def get_queryset(self):
        user = self.request.user
        if getattr(self, 'swagger_fake_view', False):
            return User.objects.none()  # or any other logic for swagger fake view
        if self.request.method == 'POST':
            # allow to register
            return User.objects.none()
        if user.is_anonymous:
            # raise with proper message provided by DRF
            raise exceptions.NotAuthenticated
        if user.is_superuser:
            return User.objects.all()
        return User.objects.filter(pk=user.pk)

# 商品视图, readonly for users
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

# 购物车视图
class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user.pk)
    
    def perform_create(self, serializer):
        serializer.save(cart=Cart.objects.get(user=self.request.user))

# JWT 登录视图
class LoginView(TokenObtainPairView):
    #XXX: workaround for drf-yasg not generating response schema for TokenObtainPairView
    @swagger_auto_schema(
        responses={
            200: openapi.Response(
                description="Login successful",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                        'access': openapi.Schema(type=openapi.TYPE_STRING, description="Access token"),
                    }
                )
            ),
            401:  openapi.Response(
                description="Unauthorized",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'detail': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description="Error message",
                            enum=[
                                "No active account found with the given credentials"
                            ]),
                    }
                ),
            )
        }
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
