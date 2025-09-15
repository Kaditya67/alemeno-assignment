# loans/utils.py
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from .models import Loan, Customer
from django.db import models

def calculate_emi(principal: float, annual_rate_percent: float, tenure_months: int) -> float:
    """
    Compound-interest based EMI formula.
    Returns EMI as float rounded to 2 decimals.
    """
    P = float(principal)
    if tenure_months <= 0:
        return 0.0
    r = float(annual_rate_percent) / 100.0 / 12.0
    if r == 0:
        emi = P / tenure_months
    else:
        emi = P * r * (1 + r) ** tenure_months / ((1 + r) ** tenure_months - 1)
    return round(emi, 2)

def months_between(today: date, end: date) -> int:
    """Rough but accurate month difference (whole months left)."""
    if end < today:
        return 0
    months = (end.year - today.year) * 12 + (end.month - today.month)
    # if day in end earlier than today, reduce one month
    if end.day < today.day:
        months -= 1
    return max(0, months)

def sum_current_loans_amount(customer: Customer) -> float:
    qs = Loan.objects.filter(customer=customer, is_active=True)
    return float(qs.aggregate(total=models.Sum('loan_amount'))['total'] or 0.0)

def sum_current_emis(customer: Customer) -> float:
    qs = Loan.objects.filter(customer=customer, is_active=True)
    return float(qs.aggregate(total=models.Sum('monthly_repayment'))['total'] or 0.0)

def compute_credit_score(customer: Customer) -> float:
    """
    Deterministic credit score in [0,100] based on:
    - on-time payment ratio (40%)
    - number of past loans (15%) (fewer -> better)
    - loan activity in current year (20%) (more -> worse)
    - loan approved volume relative to approved_limit (25%) (smaller -> better)

    Assumptions:
    - uses ALL loans (past + existing) for on-time ratio / counts
    - if sum_current_loans_amount > approved_limit -> returns 0 (as per assignment)
    """
    from django.db.models import Sum
    today = timezone.now().date()

    # quick override: too-much-current-loans
    current_sum = sum_current_loans_amount(customer)
    try:
        approved_limit = float(customer.approved_limit)
    except Exception:
        approved_limit = 0.0
    if approved_limit > 0 and current_sum > approved_limit:
        return 0.0

    loans = Loan.objects.filter(customer=customer)
    loans_count = loans.count()

    # on-time ratio:
    total_on_time = loans.aggregate(total_on=Sum('emis_paid_on_time'))['total_on'] or 0
    total_tenures = loans.aggregate(total_ten=Sum('tenure'))['total_ten'] or 0
    if total_tenures == 0:
        on_time_ratio = 1.0
    else:
        on_time_ratio = float(total_on_time) / float(total_tenures)
        on_time_ratio = min(1.0, max(0.0, on_time_ratio))
    on_time_score = on_time_ratio * 100  # 0..100

    # loans count score: fewer loans -> higher score
    # map loans_count 0 -> 100, 20+ -> 0 (linear)
    cap = 20
    loans_count_score = max(0.0, 100.0 * (1.0 - min(loans_count, cap) / cap))

    # loan activity in current year: more activity reduces score
    year_start = date(today.year, 1, 1)
    activity_count = loans.filter(start_date__gte=year_start).count()
    # map 0 -> 100, 5+ -> 0
    activity_cap = 5
    activity_score = max(0.0, 100.0 * (1.0 - min(activity_count, activity_cap) / activity_cap))

    # approved volume score: relative to approved limit: lower fraction => higher score
    vol_score = 0.0
    if approved_limit > 0:
        frac = current_sum / approved_limit
        frac = min(1.0, max(0.0, frac))
        vol_score = (1.0 - frac) * 100.0
    else:
        vol_score = 0.0

    # Weights
    score = (
        0.40 * on_time_score +
        0.15 * loans_count_score +
        0.20 * activity_score +
        0.25 * vol_score
    )

    # clamp
    return round(max(0.0, min(100.0, score)), 2)

def apply_interest_slab(credit_score: float, provided_rate: float):
    """
    Returns (approved_by_slab: bool, corrected_rate: float or None, slab_min_rate: float or None)
    Following assignment rules:
    - score > 50: approve (no slab minimum)
    - 30 < score <= 50: allowed if interest_rate > 12% (lowest slab = 12)
    - 10 < score <= 30: allowed if interest_rate > 16% (lowest slab = 16)
    - score <= 10: don't approve
    NOTE: if provided_rate is below slab, we return corrected_rate = slab_min (suggestion) but mark approved False.
    """
    if credit_score > 50:
        return True, float(provided_rate), None
    if 30 < credit_score <= 50:
        slab = 12.0
        if provided_rate > slab:
            return True, float(provided_rate), slab
        return False, slab, slab
    if 10 < credit_score <= 30:
        slab = 16.0
        if provided_rate > slab:
            return True, float(provided_rate), slab
        return False, slab, slab
    return False, None, None
