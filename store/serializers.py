from rest_framework import serializers
from .models import User, Product, CartItem

class UserSerializer(serializers.ModelSerializer):
    '''write only, exists for swagger doc for user register'''
    class Meta:
        model = User
        fields = '__all__'
        extra_kwargs = {'password': {'write_only': True}}
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user
    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password is not None:
            # We've `pop` above
            #validated_data['password'] = make_password(password)
            instance.set_password(password)
        return super().update(instance, validated_data)


class EquipmentChildSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    extra_price = serializers.DecimalField(max_digits=10, decimal_places=2)

class ProductSerializer(serializers.ModelSerializer):
    
    # XXX: the following field is read-only, so no need to implement write logic
    #  just for swagger doc
    images = serializers.ListField(
        child=serializers.URLField(),
        required=True,
        min_length=0,
    )
    equipments = serializers.ListField(
        child=EquipmentChildSerializer(),
        required=True,
        min_length=0,
    )

    class Meta:
        model = Product
        #fields = '__all__'
        exclude = ['images_max_ord']

class CartItemSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()
    original_total_price = serializers.ReadOnlyField()
    cart = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = CartItem
        fields = '__all__'


class CartSerializer(serializers.ModelSerializer):
    total_price = serializers.ReadOnlyField()
    #user = serializers.ReadOnlyField()
    user = serializers.RelatedField(source='cart.user', read_only=True)

    class Meta:
        model = CartItem
        fields = ['user', 'product', 'quantity', 'total_price']

