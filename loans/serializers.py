# loans/serializers.py
from rest_framework import serializers
from .models import Customer, Loan

class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    age = serializers.IntegerField(min_value=0)
    monthly_income = serializers.DecimalField(max_digits=12, decimal_places=2)
    phone_number = serializers.CharField()

class CustomerResponseSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        # we return internal id as customer_id (assignment expects "Id of customer (int)")
        fields = ("id", "name", "age", "monthly_income", "approved_limit", "phone_number")
    def get_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

class CheckEligibilityRequestSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    loan_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    tenure = serializers.IntegerField(min_value=1)

class CheckEligibilityResponseSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    approval = serializers.BooleanField()
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    corrected_interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    tenure = serializers.IntegerField()
    monthly_installment = serializers.DecimalField(max_digits=12, decimal_places=2)
