from django.core.management.base import BaseCommand
from loans.tasks import ingest_customers, ingest_loans

class Command(BaseCommand):
    help = "Enqueue background ingestion of customer and loan data"

    def add_arguments(self, parser):
        parser.add_argument("customers_file", type=str, help="Path to customer_data.xlsx")
        parser.add_argument("loans_file", type=str, help="Path to loan_data.xlsx")

    def handle(self, *args, **options):
        customers_file = options["customers_file"]
        loans_file = options["loans_file"]

        ingest_customers.delay(customers_file)
        ingest_loans.delay(loans_file)

        self.stdout.write(self.style.SUCCESS("Ingestion tasks enqueued"))
