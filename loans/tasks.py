import pandas as pd
from celery import shared_task
from .models import Customer, Loan

@shared_task
def ingest_customers(file_path: str):
    df = pd.read_excel(file_path)

    for _, row in df.iterrows():
        Customer.objects.update_or_create(
            customer_id=row["Customer ID"],
            defaults={
                "first_name": row["First Name"],
                "last_name": row["Last Name"],
                "age": row["Age"],
                "phone_number": str(row["Phone Number"]),
                "monthly_income": row["Monthly Salary"],
                "approved_limit": row["Approved Limit"],
            },
        )
    return f"Loaded {len(df)} customers"


@shared_task
def ingest_loans(file_path: str):
    df = pd.read_excel(file_path)

    for _, row in df.iterrows():
        try:
            customer = Customer.objects.get(customer_id=row["Customer ID"])
        except Customer.DoesNotExist:
            continue  # skip loan if customer not found

        Loan.objects.update_or_create(
            loan_id=row["Loan ID"],
            defaults={
                "customer": customer,
                "loan_amount": row["Loan Amount"],
                "tenure": row["Tenure"],
                "interest_rate": row["Interest Rate"],
                "monthly_repayment": row["Monthly payment"],
                "emis_paid_on_time": row["EMIs paid on Time"],
                "start_date": row["Date of Approval"],
                "end_date": row["End Date"],
                "is_active": True,
            },
        )
    return f"Loaded {len(df)} loans"
