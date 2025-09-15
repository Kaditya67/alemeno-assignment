from django.shortcuts import render
from django.http import JsonResponse

def healthz(request):
    return JsonResponse({"status": "ok"})

# loans/views.py
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework import generics, status
from rest_framework.response import Response
from .models import Customer, Loan
from .serializers import (
    RegisterSerializer, CustomerResponseSerializer,
    CheckEligibilityRequestSerializer, CheckEligibilityResponseSerializer
)
from .utils import (
    calculate_emi, compute_credit_score, apply_interest_slab,
    sum_current_emis, months_between
)

# helper: accept either DB id (id) or external customer_id (if present)
def get_customer_by_identifier(identifier: int):
    try:
        return Customer.objects.get(id=identifier)
    except Customer.DoesNotExist:
        # try external field if you used it (customer_id)
        try:
            return Customer.objects.get(customer_id=identifier)
        except Exception:
            raise

from decimal import ROUND_HALF_UP
from decimal import Decimal, ROUND_HALF_UP
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Customer
from .serializers import RegisterSerializer


class RegisterView(APIView):
    """
    POST /register/
    - sets approved_limit = 36 * monthly_income (rounded to nearest lakh)
    """

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        monthly_income = Decimal(data["monthly_income"])

        # approved_limit = 36 * monthly_income, rounded to nearest 1,00,000
        approved = (monthly_income * Decimal(36) / Decimal(100000)) \
            .quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal(100000)

        # customer = Customer.objects.create(
        #     first_name=data["first_name"],
        #     last_name=data["last_name"],
        #     age=data["age"],
        #     phone_number=data["phone_number"],
        #     monthly_income=monthly_income,
        #     approved_limit=approved
        # )
        last_customer = Customer.objects.order_by("-customer_id").first()
        next_customer_id = (last_customer.customer_id + 1) if last_customer else 1

        customer = Customer.objects.create(
            customer_id=next_customer_id,
            first_name=data["first_name"],
            last_name=data["last_name"],
            age=data["age"],
            phone_number=data["phone_number"],
            monthly_income=monthly_income,
            approved_limit=approved
        )


        out = {
            "customer_id": customer.id,
            "name": f"{customer.first_name} {customer.last_name}",
            "age": customer.age,
            "monthly_income": float(customer.monthly_income),
            "approved_limit": float(customer.approved_limit),
            "phone_number": customer.phone_number,
        }
        return Response(out, status=status.HTTP_201_CREATED)

class CheckEligibilityView(APIView):
    """
    POST /api/check-eligibility
    """
    def post(self, request):
        ser = CheckEligibilityRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payload = ser.validated_data

        cid = payload["customer_id"]
        try:
            customer = get_customer_by_identifier(cid)
        except Customer.DoesNotExist:
            return Response({"error": "customer not found"}, status=status.HTTP_404_NOT_FOUND)

        # compute credit score
        credit_score = compute_credit_score(customer)

        # if sum of all current EMIs > 50% monthly_income -> don't approve
        total_emis = sum_current_emis(customer)
        monthly_income = float(customer.monthly_income)
        if total_emis > 0.5 * monthly_income:
            # compute installment for completeness using provided rate
            monthly_installment = calculate_emi(float(payload["loan_amount"]), float(payload["interest_rate"]), int(payload["tenure"]))
            resp = {
                "customer_id": customer.id,
                "approval": False,
                "interest_rate": float(payload["interest_rate"]),
                "corrected_interest_rate": None,
                "tenure": payload["tenure"],
                "monthly_installment": monthly_installment,
                "reason": "existing EMIs exceed 50% of monthly income"
            }
            return Response(resp, status=status.HTTP_200_OK)

        # apply slab
        provided_rate = float(payload["interest_rate"])
        approved_by_slab, corrected_rate, slab_min = apply_interest_slab(credit_score, provided_rate)

        # If apply_interest_slab returned corrected_rate as suggestion, we use corrected_rate for installment calculation only if approved_by_slab is True.
        used_rate_for_emi = provided_rate if approved_by_slab else (corrected_rate if corrected_rate else provided_rate)

        monthly_installment = calculate_emi(float(payload["loan_amount"]), used_rate_for_emi, int(payload["tenure"]))

        resp = {
            "customer_id": customer.id,
            "approval": bool(approved_by_slab),
            "interest_rate": float(provided_rate),
            "corrected_interest_rate": float(corrected_rate) if corrected_rate is not None else None,
            "tenure": payload["tenure"],
            "monthly_installment": monthly_installment,
            "credit_score": credit_score
        }
        return Response(resp, status=status.HTTP_200_OK)

class CreateLoanView(APIView):
    """
    POST /api/create-loan
    Performs the eligibility checks and inserts loan if approved
    """
    def post(self, request):
        ser = CheckEligibilityRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        payload = ser.validated_data

        cid = payload["customer_id"]
        try:
            customer = get_customer_by_identifier(cid)
        except Customer.DoesNotExist:
            return Response({"error": "customer not found"}, status=status.HTTP_404_NOT_FOUND)

        # Reuse eligibility logic (compute score + slab)
        credit_score = compute_credit_score(customer)
        total_emis = sum_current_emis(customer)
        monthly_income = float(customer.monthly_income)
        if total_emis > 0.5 * monthly_income:
            return Response({
                "loan_id": None,
                "customer_id": customer.id,
                "loan_approved": False,
                "message": "Existing EMIs exceed 50% of monthly income",
                "monthly_installment": None
            }, status=status.HTTP_200_OK)

        provided_rate = float(payload["interest_rate"])
        approved_by_slab, corrected_rate, slab_min = apply_interest_slab(credit_score, provided_rate)

        if not approved_by_slab:
            return Response({
                "loan_id": None,
                "customer_id": customer.id,
                "loan_approved": False,
                "message": f"Not approved by credit slab (credit_score={credit_score})",
                "monthly_installment": None
            }, status=status.HTTP_200_OK)

        # approved -> create Loan
        # determine loan monthly installment using provided_rate (or corrected_rate if that is what's used)
        used_rate = provided_rate if approved_by_slab else (corrected_rate or provided_rate)
        monthly_installment = calculate_emi(float(payload["loan_amount"]), used_rate, int(payload["tenure"]))

        # create loan object (we will generate loan_id as unique external id)
        with transaction.atomic():
            max_external = Loan.objects.aggregate(max_id=models.Max('loan_id'))['max_id'] or 0
            new_external_loan_id = int(max_external) + 1
            loan = Loan.objects.create(
                customer=customer,
                loan_id=new_external_loan_id,
                loan_amount=payload["loan_amount"],
                tenure=payload["tenure"],
                interest_rate=used_rate,
                monthly_repayment=Decimal(monthly_installment),
                emis_paid_on_time=0,
                start_date=timezone.now().date(),
                # approximate end_date by adding months:
                end_date=(timezone.now().date().replace(day=1) + timedelta(days=payload["tenure"] * 30)),
                is_active=True
            )

        return Response({
            "loan_id": loan.loan_id,
            "customer_id": customer.id,
            "loan_approved": True,
            "message": "Loan approved",
            "monthly_installment": float(monthly_installment)
        }, status=status.HTTP_201_CREATED)

# Details views
class ViewLoanAPIView(APIView):
    def get(self, request, loan_id):
        try:
            loan = Loan.objects.select_related('customer').get(loan_id=loan_id)
        except Loan.DoesNotExist:
            return Response({"error": "loan not found"}, status=status.HTTP_404_NOT_FOUND)

        cust = loan.customer
        monthly_installment = float(loan.monthly_repayment)
        resp = {
            "loan_id": loan.loan_id,
            "customer": {
                "id": cust.id,
                "first_name": cust.first_name,
                "last_name": cust.last_name,
                "phone_number": cust.phone_number,
                "age": cust.age
            },
            "loan_amount": float(loan.loan_amount),
            "interest_rate": float(loan.interest_rate),
            "monthly_installment": monthly_installment,
            "tenure": loan.tenure
        }
        return Response(resp, status=status.HTTP_200_OK)

class ViewLoansByCustomerAPIView(APIView):
    def get(self, request, customer_id):
        try:
            customer = get_customer_by_identifier(customer_id)
            print(f"Customer id: {customer_id}")
        except Customer.DoesNotExist:
            return Response({"error": "customer not found"}, status=status.HTTP_404_NOT_FOUND)

        loans = Loan.objects.filter(customer=customer, is_active=True)
        today = timezone.now().date()
        out = []
        for l in loans:
            repayments_left = months_between(today, l.end_date)
            out.append({
                "loan_id": l.loan_id,
                "loan_amount": float(l.loan_amount),
                "interest_rate": float(l.interest_rate),
                "monthly_installment": float(l.monthly_repayment),
                "repayments_left": repayments_left
            })
        return Response(out, status=status.HTTP_200_OK)
