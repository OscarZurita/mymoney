from decimal import Decimal, InvalidOperation

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ExpenseForm, SignUpForm
from .models import Category, Expense


SORT_OPTIONS = {
    "date_desc": ("-date", "-id"),
    "date_asc": ("date", "id"),
    "amount_desc": ("-amount", "-id"),
    "amount_asc": ("amount", "id"),
    "category_asc": ("category__name", "date", "id"),
    "category_desc": ("-category__name", "date", "id"),
}


def _parse_decimal(value):
    if not value:
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return None


def _sort_querystring(get_params, sort_value):
    params = get_params.copy()
    params["sort"] = sort_value
    return params.urlencode()


def _parse_month_year(value):
    if not value or len(value) != 7 or value[4] != "-":
        return None, None
    year_part, month_part = value.split("-", 1)
    if not (year_part.isdigit() and month_part.isdigit()):
        return None, None
    month_int = int(month_part)
    if month_int < 1 or month_int > 12:
        return None, None
    return int(year_part), month_int

@login_required
def index(request):
    expenses = (
        Expense.objects.filter(owner=request.user)
        .select_related("category")
    )
    categories = Category.objects.order_by("name")

    exact_date = request.GET.get("date", "").strip()
    month_year = request.GET.get("month_year", "").strip()
    year = request.GET.get("year", "").strip()
    category_id = request.GET.get("category", "").strip()
    amount_min = request.GET.get("amount_min", "").strip()
    amount_max = request.GET.get("amount_max", "").strip()

    if exact_date:
        expenses = expenses.filter(date=exact_date)
    month_year_value, month_value = _parse_month_year(month_year)
    if month_year_value is not None and month_value is not None:
        expenses = expenses.filter(date__year=month_year_value, date__month=month_value)
    if year.isdigit():
        expenses = expenses.filter(date__year=int(year))
    if category_id.isdigit():
        expenses = expenses.filter(category_id=int(category_id))

    min_amount_value = _parse_decimal(amount_min)
    max_amount_value = _parse_decimal(amount_max)
    if min_amount_value is not None:
        expenses = expenses.filter(amount__gte=min_amount_value)
    if max_amount_value is not None:
        expenses = expenses.filter(amount__lte=max_amount_value)

    sort = request.GET.get("sort", "date_desc")
    expenses = expenses.order_by(*SORT_OPTIONS.get(sort, SORT_OPTIONS["date_desc"]))

    context = {
        "expenses": expenses,
        "categories": categories,
        "filters": {
            "date": exact_date,
            "month_year": month_year,
            "year": year,
            "category": category_id,
            "amount_min": amount_min,
            "amount_max": amount_max,
        },
        "current_sort": sort,
        "date_sort_query": _sort_querystring(
            request.GET,
            "date_asc" if sort == "date_desc" else "date_desc",
        ),
        "amount_sort_query": _sort_querystring(
            request.GET,
            "amount_asc" if sort == "amount_desc" else "amount_desc",
        ),
        "category_sort_query": _sort_querystring(
            request.GET,
            "category_asc" if sort == "category_desc" else "category_desc",
        ),
        "has_active_filters": any(
            [exact_date, month_year, year, category_id, amount_min, amount_max]
        ),
    }
    return render(request, "money_app/index.html", context)


@login_required
def add_expense(request):
    form = ExpenseForm()

    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.owner = request.user
            expense.save()
            return redirect("money_app:index")

    return render(request, "money_app/add_expense.html", {"form": form})


@login_required
def delete_expense(request, expense_id):
    if request.method != "POST":
        return redirect("money_app:index")

    expense = get_object_or_404(Expense, pk=expense_id, owner=request.user)
    expense.delete()
    return redirect("money_app:index")

@login_required
def edit_expense(request, expense_id):
    expense = get_object_or_404(Expense,pk = expense_id, owner = request.user)
    form = ExpenseForm(request.POST or None, instance = expense)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            return redirect("money_app:index")
    return render(request, "money_app/add_expense.html", {"form": form})

@login_required
def landing_page(request):
    expenses = Expense.objects.filter(owner=request.user)
    return render(request, "money_app/landing_page.html")

@login_required
def analysis(request):
    expenses = Expense.objects.filter(owner=request.user).select_related("category")

    selected_year = request.GET.get("year", "").strip()
    if selected_year.isdigit():
        expenses = expenses.filter(date__year=int(selected_year))

    summary = expenses.aggregate(
        total_spent=Sum("amount"),
        average_expense=Avg("amount"),
        highest_expense=Max("amount"),
        total_expenses=Count("id"),
    )

    monthly_totals = (
        expenses.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-month")
    )

    category_breakdown = (
        expenses.values("category__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total", "category__name")
    )

    largest_expenses = expenses.order_by("-amount", "-date", "-id")[:5]
    available_years = (
        Expense.objects.filter(owner=request.user)
        .dates("date", "year", order="DESC")
    )

    context = {
        "summary": summary,
        "monthly_totals": monthly_totals,
        "category_breakdown": category_breakdown,
        "largest_expenses": largest_expenses,
        "available_years": available_years,
        "selected_year": selected_year,
    }
    return render(request, "money_app/analysis.html", context)


def signup(request):
    form = SignUpForm()

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("money_app:index")

    return render(request, "registration/signup.html", {"form": form})
