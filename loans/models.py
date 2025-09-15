from django.db import models

class Customer(models.Model):
    # Django auto PK (id) stays
    customer_id = models.IntegerField(unique=True, db_index=True)  # Excel’s Customer ID
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    age = models.PositiveIntegerField()
    phone_number = models.CharField(max_length=15, unique=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2)
    approved_limit = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.customer_id})"


class Loan(models.Model):
    # FK links to Django's internal ID
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="loans")

    loan_id = models.IntegerField(unique=True, db_index=True)  # Excel’s Loan ID
    loan_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tenure = models.PositiveIntegerField(help_text="Tenure in months")
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, help_text="Annual %")
    monthly_repayment = models.DecimalField(max_digits=12, decimal_places=2)
    emis_paid_on_time = models.PositiveIntegerField(default=0)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Loan {self.loan_id} for {self.customer.first_name}"
