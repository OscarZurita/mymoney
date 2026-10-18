from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Debt

RECENTLY_SETTLED_LIMIT = 20


@login_required
def debts(request):
    user_debts = Debt.objects.filter(expense__user=request.user).select_related(
        "person", "expense__category"
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

    context = {
        "totals": open_debts.aggregate(owed_to_me=owed_to_me, owed_by_me=owed_by_me),
        "balances": balances,
        "open_debts": open_debts.order_by("person__name", "-expense__date", "-id"),
        "recently_settled": user_debts.filter(settled_on__isnull=False).order_by(
            "-settled_on", "-id"
        )[:RECENTLY_SETTLED_LIMIT],
    }
    return render(request, "money_app/debts.html", context)


@login_required
def settle_debt(request, debt_id):
    return _set_settled(request, debt_id, True)


@login_required
def reopen_debt(request, debt_id):
    return _set_settled(request, debt_id, False)


def _set_settled(request, debt_id, settled):
    # Like the delete views, a GET only redirects and never changes data.
    if request.method == "POST":
        debt = get_object_or_404(Debt, pk=debt_id, expense__user=request.user)
        debt.set_settled(settled)
        debt.save(update_fields=["settled_on"])
    return redirect("money_app:debts")
