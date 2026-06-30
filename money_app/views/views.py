from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ._utils import clamp, format_decimal, format_percent, polar_to_cartesian, format_point, donut_slice_path, parse_decimal, sort_querystring, parse_month_year, build_monthly_chart, build_category_chart

from ..forms import ExpenseForm, IncomeForm, SignUpForm, YearGoalForm
from ..models import Category, Expense, ExpenseTag, YearGoal


SORT_OPTIONS = {
    "date_desc": ("-date", "-id"),
    "date_asc": ("date", "id"),
    "amount_desc": ("-amount", "-id"),
    "amount_asc": ("amount", "id"),
    "category_asc": ("category__name", "date", "id"),
    "category_desc": ("-category__name", "date", "id"),
}
from .transactions import (
    ExpenseListView, ExpenseCreateView, ExpenseUpdateView, ExpenseDeleteView,
    IncomeListView, IncomeCreateView, IncomeUpdateView, IncomeDeleteView,
    InvestmentListView, InvestmentCreateView, InvestmentUpdateView, InvestmentDeleteView
)

index = ExpenseListView.as_view()
add_expense = ExpenseCreateView.as_view()
edit_expense = ExpenseUpdateView.as_view()
delete_expense = ExpenseDeleteView.as_view()
    

@login_required
def dashboard(request):
    today = timezone.localdate()

    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    year_expenses = Expense.objects.filter(user=request.user, date__gte=start_of_year)
    month_expenses = year_expenses.filter(date__gte=start_of_month)
    
    def total(qs):
        return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    month_total = total(month_expenses)
    ytd_total = total(year_expenses)
    year_goal = YearGoal.objects.filter(user=request.user, year=today.year).first()
    monthly_goal = None
    monthly_goal_percent = Decimal("0")
    monthly_goal_progress_width = "0"
    ytd_goal_percent = Decimal("0")
    ytd_goal_progress_width = "0"

    if year_goal is not None:
        monthly_goal = year_goal.amount / Decimal("12")
        if monthly_goal > 0:
            monthly_goal_percent = (month_total / monthly_goal) * Decimal("100")
            monthly_goal_progress_width = format_percent(
                min(monthly_goal_percent, Decimal("100"))
            )
        if year_goal.amount > 0:
            ytd_goal_percent = (ytd_total / year_goal.amount) * Decimal("100")
            ytd_goal_progress_width = format_percent(
                min(ytd_goal_percent, Decimal("100"))
            )
    
    # day/cat table. Retrieve and build matrix to pass to the template
    cat_day_sum = (month_expenses.values("category__name").annotate(total=Sum("amount")).order_by("date","category__name"))
    tot_by_cat = {row["category__name"]: row["total"] for row in cat_day_sum}
    categories = list(Category.objects.values_list("name", flat=True).order_by("name"))
    table_data = [
        {"category": cat, "total": tot_by_cat.get(cat, Decimal("0"))}
        for cat in categories
    ]
    
    print(table_data)
    
    context = {
        "month_total": month_total,
        "year_goal": year_goal,
        "monthly_goal": monthly_goal,
        "monthly_goal_percent": format_percent(monthly_goal_percent),
        "monthly_goal_progress_width": monthly_goal_progress_width,
        "monthly_goal_is_over": monthly_goal_percent > Decimal("100"),
        "ytd_total": ytd_total,
        "ytd_goal_percent": format_percent(ytd_goal_percent),
        "ytd_goal_progress_width": ytd_goal_progress_width,
        "ytd_goal_is_over": ytd_goal_percent > Decimal("100"),
        "cat_day_rows": table_data
    }
    return render(request, "money_app/dashboard.html", context)

@login_required
def add_year_goal(request):
    form = YearGoalForm(user=request.user)

    if request.method == "POST":
        form = YearGoalForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            return redirect("money_app:dashboard")

    return render(request, "money_app/add_year_goal.html", {"form": form})

@login_required
def year_goals(request):
    goals = list(YearGoal.objects.filter(user=request.user).order_by("-year"))
    goal_years = [goal.year for goal in goals]

    expense_totals = {
        row["date__year"]: row["total"] or Decimal("0")
        for row in (
            Expense.objects.filter(user=request.user, date__year__in=goal_years)
            .values("date__year")
            .annotate(total=Sum("amount"))
        )
    }

    goal_rows = []
    for goal in goals:
        total_spent = expense_totals.get(goal.year, Decimal("0"))
        percent = Decimal("0")
        progress_width = "0"

        if goal.amount > 0:
            percent = (total_spent / goal.amount) * Decimal("100")
            progress_width = format_percent(min(percent, Decimal("100")))

        is_over = percent > Decimal("100")
        difference = abs(goal.amount - total_spent)
        status_label = "Over by" if is_over else "Remaining"

        goal_rows.append(
            {
                "year": goal.year,
                "goal": goal,
                "total_spent": total_spent,
                "percent": format_percent(percent),
                "progress_width": progress_width,
                "is_over": is_over,
                "difference": difference,
                "status_label": status_label,
            }
        )

    return render(
        request,
        "money_app/year_goals.html",
        {"goal_rows": goal_rows},
    )

@login_required
def analysis(request):
    expenses = Expense.objects.filter(user=request.user).select_related("category")

    today = timezone.localdate()
    current_year = today.year
    raw_selected_year = request.GET.get("year")
    selected_year = (
        str(current_year)
        if raw_selected_year is None
        else raw_selected_year.strip()
    )
    if selected_year.isdigit():
        expenses = expenses.filter(date__year=int(selected_year))

    goal_year = int(selected_year) if selected_year.isdigit() else current_year
    year_goal = YearGoal.objects.filter(user=request.user, year=goal_year).first()

    summary = expenses.aggregate(
        total_spent=Sum("amount"),
        average_expense=Avg("amount"),
        highest_expense=Max("amount"),
        total_expenses=Count("id"),
    )

    monthly_totals = list(
        expenses.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("month")
    )

    category_breakdown = list(
        expenses.values("category__name")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total", "category__name")
    )

    largest_expenses = expenses.order_by("-amount", "-date", "-id")[:5]
    available_years = list(
        Expense.objects.filter(user=request.user)
        .dates("date", "year", order="DESC")
    )
    current_year_date = today.replace(month=1, day=1)
    if current_year_date not in available_years:
        available_years.append(current_year_date)
        available_years.sort(reverse=True)

    context = {
        "goal": year_goal,
        "summary": summary,
        "monthly_totals": monthly_totals,
        "monthly_chart": build_monthly_chart(monthly_totals),
        "category_breakdown": category_breakdown,
        "category_chart": build_category_chart(category_breakdown),
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
            return redirect("money_app:expenses")

    return render(request, "registration/signup.html", {"form": form})
