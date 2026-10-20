from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Category, Debt, Person
from ._utils import parse_day, parse_decimal, parse_month_year, parse_year

RECENTLY_SETTLED_LIMIT = 20
DIRECTION_FILTER_OPTIONS = [
    (Debt.Direction.OWED_TO_ME, "Owed to you"),
    (Debt.Direction.OWED_BY_ME, "You owe"),
]


@login_required
def debts(request):
    user_debts = Debt.objects.for_user(request.user).select_related(
        "person", "expense__category", "income__category"
    )
    open_debts = user_debts.filter(settled_on__isnull=True)
    owed_to_me = Sum(
        "amount", filter=Q(direction=Debt.Direction.OWED_TO_ME), default=Decimal("0")
    )
    owed_by_me = Sum(
        "amount", filter=Q(direction=Debt.Direction.OWED_BY_ME), default=Decimal("0")
    )

    balances = []
    for row in (
        open_debts.values("person__name")
        .annotate(owed_to_me=owed_to_me, owed_by_me=owed_by_me)
        .order_by("person__name")
    ):
        net = row["owed_to_me"] - row["owed_by_me"]
        balances.append({**row, "net": abs(net), "they_owe_me": net > 0})

    # The filters narrow the two lists; the totals and balances above them stay
    # the overall picture.
    people = list(Person.objects.filter(user=request.user))
    categories = list(
        Category.objects.filter(
            type__in=[Category.Type.EXPENSE, Category.Type.INCOME]
        ).order_by("type", "name")
    )
    # The lists filter and sort by the date of the debt's expense or income.
    listed_debts = user_debts.annotate(
        transaction_date=Coalesce("expense__date", "income__date")
    )
    filters, listed_debts = filter_debts(listed_debts, request.GET, people, categories)
    settled = listed_debts.filter(settled_on__isnull=False).order_by(
        "-settled_on", "-id"
    )

    context = {
        "totals": open_debts.aggregate(owed_to_me=owed_to_me, owed_by_me=owed_by_me),
        "balances": balances,
        "has_debts": user_debts.exists(),
        "filters": filters,
        "has_active_filters": any(filters.values()),
        "people": people,
        "categories": categories,
        "direction_options": DIRECTION_FILTER_OPTIONS,
        "open_debts": listed_debts.filter(settled_on__isnull=True).order_by(
            "person__name", "-transaction_date", "-id"
        ),
        "recently_settled": settled[:RECENTLY_SETTLED_LIMIT],
        "settled_count": settled.count(),
    }
    return render(request, "money_app/debts.html", context)


def filter_debts(debts, params, people, categories):
    """Apply the filters in the query string to the debts.

    The debts must be annotated with `transaction_date`. Returns the filters
    that were applied, for the page to show, and the filtered debts. Invalid
    values are ignored rather than failing the page.
    """
    filters = {
        "date": "",
        "month_year": "",
        "year": "",
        "people": [],
        "direction": "",
        "amount_min": "",
        "amount_max": "",
        "category": "",
    }

    day = parse_day(params.get("date", "").strip())
    if day is not None:
        debts = debts.filter(transaction_date=day)
        filters["date"] = day.isoformat()

    year, month = parse_month_year(params.get("month_year", "").strip())
    if year is not None:
        debts = debts.filter(transaction_date__year=year, transaction_date__month=month)
        filters["month_year"] = f"{year:04d}-{month:02d}"

    year = parse_year(params.get("year", "").strip())
    if year is not None:
        debts = debts.filter(transaction_date__year=year)
        filters["year"] = str(year)

    person_ids = {str(person.id) for person in people}
    selected_people = [
        person_id
        for person_id in dict.fromkeys(params.getlist("person"))
        if person_id in person_ids
    ]
    if selected_people:
        debts = debts.filter(person_id__in=selected_people)
        filters["people"] = selected_people

    direction = params.get("direction", "")
    if direction in Debt.Direction.values:
        debts = debts.filter(direction=direction)
        filters["direction"] = direction

    for name, lookup in (("amount_min", "amount__gte"), ("amount_max", "amount__lte")):
        raw_amount = params.get(name, "").strip()
        amount = parse_decimal(raw_amount)
        if amount is not None:
            debts = debts.filter(**{lookup: amount})
            filters[name] = raw_amount

    category = params.get("category", "")
    if category in {str(option.id) for option in categories}:
        debts = debts.filter(
            Q(expense__category_id=category) | Q(income__category_id=category)
        )
        filters["category"] = category

    return filters, debts


@login_required
def settle_debt(request, debt_id):
    return _set_settled(request, debt_id, True)


@login_required
def reopen_debt(request, debt_id):
    return _set_settled(request, debt_id, False)


def _set_settled(request, debt_id, settled):
    # Like the delete views, a GET only redirects and never changes data.
    if request.method == "POST":
        debt = get_object_or_404(Debt.objects.for_user(request.user), pk=debt_id)
        debt.set_settled(settled)
        debt.save(update_fields=["settled_on"])
    return redirect("money_app:debts")
