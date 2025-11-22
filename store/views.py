from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status, viewsets
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, Product, CartItem, Cart, product_images_url
from .serializers import UserSerializer, ProductSerializer, UserLoginSerializer, CartItemSerializer
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

# 用户注册
class RegisterView(APIView):
    @swagger_auto_schema(
            request_body=UserSerializer,
            responses={
                201: UserSerializer,
                400: openapi.Response(
                    description="Bad Request, with validation errors message for specific field",
                    schema=openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            'username': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_STRING)),
                            'email': openapi.Schema(type=openapi.TYPE_ARRAY, items=openapi.Items(type=openapi.TYPE_STRING)),
                        }
                    )
                )
            }
    )
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
class LoginView(APIView):
    _M_USER_NOT_FOUND = 'User not found'
    @swagger_auto_schema(
        request_body=UserLoginSerializer,
        responses={
            200: openapi.Response(
                description="Login successful",
                schema=openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        #'refresh': openapi.Schema(type=openapi.TYPE_STRING),
                        'token': openapi.Schema(type=openapi.TYPE_STRING, description="Access token"),
                    }
                )
            ),
            401: "Invalid credentials",
            404: _M_USER_NOT_FOUND,
        }
    )
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = User.objects.filter(username=username).first()
        if user is None:
            return Response(self._M_USER_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        if not user.check_password(password):
            return Response('Invalid credentials', status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        return Response({
            #'refresh': str(refresh),
            'token': str(refresh.access_token),
        })
