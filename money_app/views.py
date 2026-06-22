import math
from decimal import Decimal, InvalidOperation

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Max, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict
import calendar

from .forms import ExpenseForm, SignUpForm, YearGoalForm
from .models import Category, Expense, Tag, YearGoal


SORT_OPTIONS = {
    "date_desc": ("-date", "-id"),
    "date_asc": ("date", "id"),
    "amount_desc": ("-amount", "-id"),
    "amount_asc": ("amount", "id"),
    "category_asc": ("category__name", "date", "id"),
    "category_desc": ("-category__name", "date", "id"),
}


CHART_COLORS = [
    "#0b57d0",
    "#14b8a6",
    "#f59e0b",
    "#ec4899",
    "#8b5cf6",
    "#22c55e",
    "#ef4444",
    "#64748b",
]


def _clamp(value, lower_bound, upper_bound):
    return max(lower_bound, min(value, upper_bound))


def _format_decimal(value):
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    quantized_value = decimal_value.quantize(Decimal("0.01"))
    if quantized_value == quantized_value.to_integral_value():
        return str(int(quantized_value))
    return format(quantized_value.normalize(), "f")


def _format_percent(value):
    return _format_decimal(value)


def _polar_to_cartesian(center_x, center_y, radius, angle_degrees):
    angle_radians = math.radians(angle_degrees - 90)
    return (
        center_x + (radius * math.cos(angle_radians)),
        center_y + (radius * math.sin(angle_radians)),
    )


def _format_point(x, y):
    return f"{_format_decimal(x)},{_format_decimal(y)}"


def _donut_slice_path(start_percent, end_percent):
    center_x = 120
    center_y = 120
    outer_radius = 100
    inner_radius = 52
    start_angle = float((start_percent / Decimal("100")) * Decimal("360"))
    end_angle = float((end_percent / Decimal("100")) * Decimal("360"))

    if end_angle - start_angle >= 359.99:
        outer_start = _polar_to_cartesian(center_x, center_y, outer_radius, 0)
        outer_mid = _polar_to_cartesian(center_x, center_y, outer_radius, 180)
        inner_start = _polar_to_cartesian(center_x, center_y, inner_radius, 0)
        inner_mid = _polar_to_cartesian(center_x, center_y, inner_radius, 180)
        return (
            f"M {_format_point(*outer_start)} "
            f"A {outer_radius} {outer_radius} 0 1 1 {_format_point(*outer_mid)} "
            f"A {outer_radius} {outer_radius} 0 1 1 {_format_point(*outer_start)} "
            f"M {_format_point(*inner_start)} "
            f"A {inner_radius} {inner_radius} 0 1 0 {_format_point(*inner_mid)} "
            f"A {inner_radius} {inner_radius} 0 1 0 {_format_point(*inner_start)}"
        )

    outer_start = _polar_to_cartesian(center_x, center_y, outer_radius, start_angle)
    outer_end = _polar_to_cartesian(center_x, center_y, outer_radius, end_angle)
    inner_start = _polar_to_cartesian(center_x, center_y, inner_radius, start_angle)
    inner_end = _polar_to_cartesian(center_x, center_y, inner_radius, end_angle)
    large_arc = 1 if end_angle - start_angle > 180 else 0

    return (
        f"M {_format_point(*outer_start)} "
        f"A {outer_radius} {outer_radius} 0 {large_arc} 1 {_format_point(*outer_end)} "
        f"L {_format_point(*inner_end)} "
        f"A {inner_radius} {inner_radius} 0 {large_arc} 0 {_format_point(*inner_start)} "
        "Z"
    )


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
        .prefetch_related("tags")
    )
    categories = Category.objects.order_by("name")
    tags = list(Tag.objects.filter(owner=request.user).order_by("name"))
    valid_tag_ids = {tag.id for tag in tags}

    exact_date = request.GET.get("date", "").strip()
    month_year = request.GET.get("month_year", "").strip()
    year = request.GET.get("year", "").strip()
    category_id = request.GET.get("category", "").strip()
    selected_tag_ids = []
    amount_min = request.GET.get("amount_min", "").strip()
    amount_max = request.GET.get("amount_max", "").strip()

    for raw_tag_id in request.GET.getlist("tag"):
        if not raw_tag_id.isdigit():
            continue
        tag_id = int(raw_tag_id)
        if tag_id not in valid_tag_ids or raw_tag_id in selected_tag_ids:
            continue
        selected_tag_ids.append(raw_tag_id)

    if exact_date:
        expenses = expenses.filter(date=exact_date)
    month_year_value, month_value = _parse_month_year(month_year)
    if month_year_value is not None and month_value is not None:
        expenses = expenses.filter(date__year=month_year_value, date__month=month_value)
    if year.isdigit():
        expenses = expenses.filter(date__year=int(year))
    if category_id.isdigit():
        expenses = expenses.filter(category_id=int(category_id))
    if selected_tag_ids:
        expenses = expenses.filter(tags__id__in=[int(tag_id) for tag_id in selected_tag_ids]).distinct()

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
        "tags": tags,
        "filters": {
            "date": exact_date,
            "month_year": month_year,
            "year": year,
            "category": category_id,
            "tags": selected_tag_ids,
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
            [exact_date, month_year, year, category_id, selected_tag_ids, amount_min, amount_max]
        ),
    }
    return render(request, "money_app/expenses.html", context)


@login_required
def add_expense(request):
    form = ExpenseForm(user=request.user)

    if request.method == "POST":
        form = ExpenseForm(request.POST, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.owner = request.user
            expense.save()
            form.save_m2m()
            return redirect("money_app:expenses")

    return render(request, "money_app/add_expense.html", {"form": form})


@login_required
def delete_expense(request, expense_id):
    if request.method != "POST":
        return redirect("money_app:expenses")

    expense = get_object_or_404(Expense, pk=expense_id, owner=request.user)
    expense.delete()
    return redirect("money_app:expenses")

@login_required
def edit_expense(request, expense_id):
    expense = get_object_or_404(Expense,pk = expense_id, owner = request.user)
    form = ExpenseForm(request.POST or None, instance=expense, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            expense = form.save(commit=False)
            expense.owner = request.user
            expense.save()
            form.save_m2m()
            return redirect("money_app:expenses")
    return render(request, "money_app/add_expense.html", {"form": form})

@login_required
def dashboard(request):
    today = timezone.localdate()

    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)

    year_expenses = Expense.objects.filter(owner=request.user, date__gte=start_of_year)
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
            monthly_goal_progress_width = _format_percent(
                min(monthly_goal_percent, Decimal("100"))
            )
        if year_goal.amount > 0:
            ytd_goal_percent = (ytd_total / year_goal.amount) * Decimal("100")
            ytd_goal_progress_width = _format_percent(
                min(ytd_goal_percent, Decimal("100"))
            )
    
    # day/cat table. Retrieve and build matrix to pass to the template
    cat_day_sum = (month_expenses.values("date", "category__name").annotate(total=Sum("amount")).order_by("date","category__name"))
    categories = list(Category.objects.values_list("name", flat=True).order_by("name"))
    table_data = defaultdict(dict)
    for row in cat_day_sum:
        day = row["date"].day
        cat = row["category__name"]
        table_data[day][cat] = row["total"]
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    table_rows = [{
            "day": day,
            "totals": [table_data[day].get(cat) for cat in categories],
            "row_total": sum(table_data[day].values())
            } for day in range(1, days_in_month + 1)]
    
    print(table_rows)
    
    context = {
        "month_total": month_total,
        "year_goal": year_goal,
        "monthly_goal": monthly_goal,
        "monthly_goal_percent": _format_percent(monthly_goal_percent),
        "monthly_goal_progress_width": monthly_goal_progress_width,
        "monthly_goal_is_over": monthly_goal_percent > Decimal("100"),
        "ytd_total": ytd_total,
        "ytd_goal_percent": _format_percent(ytd_goal_percent),
        "ytd_goal_progress_width": ytd_goal_progress_width,
        "ytd_goal_is_over": ytd_goal_percent > Decimal("100"),
        "categories": categories,
        "cat_day_rows": table_rows
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
            Expense.objects.filter(owner=request.user, date__year__in=goal_years)
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
            progress_width = _format_percent(min(percent, Decimal("100")))

        is_over = percent > Decimal("100")
        difference = abs(goal.amount - total_spent)
        status_label = "Over by" if is_over else "Remaining"

        goal_rows.append(
            {
                "year": goal.year,
                "goal": goal,
                "total_spent": total_spent,
                "percent": _format_percent(percent),
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


def _build_monthly_chart(monthly_totals):
    if not monthly_totals:
        return None

    chart_width = Decimal("640")
    chart_height = Decimal("260")
    chart_left = Decimal("44")
    chart_right = Decimal("18")
    chart_top = Decimal("18")
    chart_bottom = Decimal("36")
    plot_width = chart_width - chart_left - chart_right
    plot_height = chart_height - chart_top - chart_bottom
    baseline_y = chart_top + plot_height

    max_total = max(row["total"] or Decimal("0") for row in monthly_totals)
    chart_max = max_total if max_total > 0 else Decimal("1")
    point_count = len(monthly_totals)
    chart_rows = []

    for index, row in enumerate(monthly_totals):
        total = row["total"] or Decimal("0")
        x_ratio = (
            Decimal("0.5")
            if point_count == 1
            else Decimal(index) / Decimal(point_count - 1)
        )
        y_ratio = total / chart_max
        x = chart_left + (plot_width * x_ratio)
        y = chart_top + (plot_height * (Decimal("1") - y_ratio))
        tooltip_width = Decimal("150")
        tooltip_height = Decimal("42")
        tooltip_x = _clamp(
            x - (tooltip_width / Decimal("2")),
            Decimal("4"),
            chart_width - tooltip_width - Decimal("4"),
        )
        tooltip_y = y + Decimal("14") if y < Decimal("78") else y - tooltip_height - Decimal("12")

        chart_rows.append(
            {
                "month": row["month"],
                "total": total,
                "count": row["count"],
                "x": _format_decimal(x),
                "y": _format_decimal(y),
                "tooltip_x": _format_decimal(tooltip_x),
                "tooltip_y": _format_decimal(tooltip_y),
                "tooltip_text_x": _format_decimal(tooltip_x + (tooltip_width / Decimal("2"))),
                "tooltip_title_y": _format_decimal(tooltip_y + Decimal("16")),
                "tooltip_detail_y": _format_decimal(tooltip_y + Decimal("31")),
            }
        )

    line_points = " ".join(f"{row['x']},{row['y']}" for row in chart_rows)
    area_points = (
        f"{chart_rows[0]['x']},{_format_decimal(baseline_y)} "
        f"{line_points} "
        f"{chart_rows[-1]['x']},{_format_decimal(baseline_y)}"
    )

    return {
        "rows": chart_rows,
        "line_points": line_points,
        "area_points": area_points,
        "max_total": max_total,
        "baseline_y": _format_decimal(baseline_y),
    }


def _build_category_chart(category_breakdown):
    if not category_breakdown:
        return None

    category_total = sum(
        (row["total"] or Decimal("0") for row in category_breakdown),
        Decimal("0"),
    )
    if category_total <= 0:
        return None

    chart_rows = []
    running_percent = Decimal("0")

    for index, row in enumerate(category_breakdown):
        total = row["total"] or Decimal("0")
        percent = (total / category_total) * Decimal("100")
        start_percent = running_percent
        running_percent += percent
        end_percent = (
            Decimal("100")
            if index == len(category_breakdown) - 1
            else running_percent
        )
        color = CHART_COLORS[index % len(CHART_COLORS)]
        name = row["category__name"] or "Uncategorized"
        midpoint_percent = (start_percent + end_percent) / Decimal("2")
        midpoint_angle = float((midpoint_percent / Decimal("100")) * Decimal("360"))
        tooltip_anchor = _polar_to_cartesian(120, 120, 76, midpoint_angle)
        tooltip_width = 124
        tooltip_height = 48
        tooltip_x = _clamp(tooltip_anchor[0] - (tooltip_width / 2), 4, 240 - tooltip_width - 4)
        tooltip_y = _clamp(tooltip_anchor[1] - (tooltip_height / 2), 4, 240 - tooltip_height - 4)

        chart_rows.append(
            {
                "name": name,
                "total": total,
                "count": row["count"],
                "percent": _format_percent(percent),
                "color": color,
                "path": _donut_slice_path(start_percent, end_percent),
                "tooltip_x": _format_decimal(tooltip_x),
                "tooltip_y": _format_decimal(tooltip_y),
                "tooltip_text_x": _format_decimal(tooltip_x + (tooltip_width / 2)),
                "tooltip_title_y": _format_decimal(tooltip_y + 16),
                "tooltip_detail_y": _format_decimal(tooltip_y + 32),
            }
        )

    return {
        "rows": chart_rows,
        "total": category_total,
    }


@login_required
def analysis(request):
    expenses = Expense.objects.filter(owner=request.user).select_related("category")

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
        Expense.objects.filter(owner=request.user)
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
        "monthly_chart": _build_monthly_chart(monthly_totals),
        "category_breakdown": category_breakdown,
        "category_chart": _build_category_chart(category_breakdown),
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
