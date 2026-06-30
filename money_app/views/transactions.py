from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from decimal import Decimal

from ..models import Category, Expense, Income, Investment, ExpenseTag, IncomeTag, InvestmentTag
from ..forms import ExpenseForm, IncomeForm, InvestmentForm
from ._utils import parse_month_year, parse_decimal, sort_querystring

SORT_OPTIONS = {
    "date_desc": ("-date", "-id"),
    "date_asc": ("date", "id"),
    "amount_desc": ("-amount", "-id"),
    "amount_asc": ("amount", "id"),
    "category_asc": ("category__name", "date", "id"),
    "category_desc": ("-category__name", "date", "id"),
}

class TransactionListView(LoginRequiredMixin, View):
    model = None
    tag_model = None
    category_type = None
    template_name = "money_app/transactions.html"
    context_object_name = "transactions"
    
    # URL names for reverse routing
    list_url_name = None
    add_url_name = None
    edit_url_name = None
    delete_url_name = None
    
    # Context title/labels
    transaction_type_label = None
    transaction_type_plural = None

    def get(self, request, *args, **kwargs):
        if not self.model or not self.tag_model or not self.category_type:
            raise NotImplementedError("Subclasses must define model, tag_model, and category_type.")

        queryset = (
            self.model.objects.filter(user=request.user)
            .select_related("category")
            .prefetch_related("tags")
        )
        categories = Category.objects.filter(type=self.category_type).order_by("name")
        tags = list(self.tag_model.objects.filter(user=request.user).order_by("name"))
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
            queryset = queryset.filter(date=exact_date)
        month_year_value, month_value = parse_month_year(month_year)
        if month_year_value is not None and month_value is not None:
            queryset = queryset.filter(date__year=month_year_value, date__month=month_value)
        if year.isdigit():
            queryset = queryset.filter(date__year=int(year))
        if category_id.isdigit():
            queryset = queryset.filter(category_id=int(category_id))
        if selected_tag_ids:
            queryset = queryset.filter(tags__id__in=[int(tag_id) for tag_id in selected_tag_ids]).distinct()

        min_amount_value = parse_decimal(amount_min)
        max_amount_value = parse_decimal(amount_max)
        if min_amount_value is not None:
            queryset = queryset.filter(amount__gte=min_amount_value)
        if max_amount_value is not None:
            queryset = queryset.filter(amount__lte=max_amount_value)

        sort = request.GET.get("sort", "date_desc")
        queryset = queryset.order_by(*SORT_OPTIONS.get(sort, SORT_OPTIONS["date_desc"]))

        context = {
            self.context_object_name: queryset,
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
            "date_sort_query": sort_querystring(
                request.GET,
                "date_asc" if sort == "date_desc" else "date_desc",
            ),
            "amount_sort_query": sort_querystring(
                request.GET,
                "amount_asc" if sort == "amount_desc" else "amount_desc",
            ),
            "category_sort_query": sort_querystring(
                request.GET,
                "category_asc" if sort == "category_desc" else "category_desc",
            ),
            "has_active_filters": any(
                [exact_date, month_year, year, category_id, selected_tag_ids, amount_min, amount_max]
            ),
            "transaction_type_label": self.transaction_type_label,
            "transaction_type_plural": self.transaction_type_plural,
            "list_url_name": self.list_url_name,
            "add_url_name": self.add_url_name,
            "edit_url_name": self.edit_url_name,
            "delete_url_name": self.delete_url_name,
        }
        return render(request, self.template_name, context)

class TransactionCreateView(LoginRequiredMixin, View):
    form_class = None
    template_name = "money_app/add_transaction.html"
    success_url_name = None
    transaction_type_label = None
    transaction_type_plural = None

    def get(self, request, *args, **kwargs):
        if not self.form_class or not self.success_url_name:
            raise NotImplementedError("Subclasses must define form_class and success_url_name.")
        
        form = self.form_class(user=request.user)
        return render(request, self.template_name, {
            "form": form,
            "transaction_type_label": self.transaction_type_label,
            "transaction_type_plural": self.transaction_type_plural,
            "success_url_name": self.success_url_name,
        })

    def post(self, request, *args, **kwargs):
        if not self.form_class or not self.success_url_name:
            raise NotImplementedError("Subclasses must define form_class and success_url_name.")

        form = self.form_class(request.POST, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            form.save_m2m()
            return redirect(self.success_url_name)
        
        return render(request, self.template_name, {
            "form": form,
            "transaction_type_label": self.transaction_type_label,
            "transaction_type_plural": self.transaction_type_plural,
            "success_url_name": self.success_url_name,
        })

class TransactionUpdateView(LoginRequiredMixin, View):
    model = None
    form_class = None
    template_name = "money_app/add_transaction.html"
    success_url_name = None
    pk_url_kwarg = None
    transaction_type_label = None
    transaction_type_plural = None

    def get_object(self, request, kwargs):
        pk = kwargs.get(self.pk_url_kwarg)
        return get_object_or_404(self.model, pk=pk, user=request.user)

    def get(self, request, *args, **kwargs):
        if not self.model or not self.form_class or not self.success_url_name or not self.pk_url_kwarg:
            raise NotImplementedError("Subclasses must define model, form_class, success_url_name, and pk_url_kwarg.")

        obj = self.get_object(request, kwargs)
        form = self.form_class(instance=obj, user=request.user)
        return render(request, self.template_name, {
            "form": form,
            "transaction_type_label": self.transaction_type_label,
            "transaction_type_plural": self.transaction_type_plural,
            "success_url_name": self.success_url_name,
        })

    def post(self, request, *args, **kwargs):
        if not self.model or not self.form_class or not self.success_url_name or not self.pk_url_kwarg:
            raise NotImplementedError("Subclasses must define model, form_class, success_url_name, and pk_url_kwarg.")

        obj = self.get_object(request, kwargs)
        form = self.form_class(request.POST, instance=obj, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            form.save_m2m()
            return redirect(self.success_url_name)
        
        return render(request, self.template_name, {
            "form": form,
            "transaction_type_label": self.transaction_type_label,
            "transaction_type_plural": self.transaction_type_plural,
            "success_url_name": self.success_url_name,
        })

class TransactionDeleteView(LoginRequiredMixin, View):
    model = None
    success_url_name = None
    pk_url_kwarg = None

    def post(self, request, *args, **kwargs):
        if not self.model or not self.success_url_name or not self.pk_url_kwarg:
            raise NotImplementedError("Subclasses must define model, success_url_name, and pk_url_kwarg.")

        pk = kwargs.get(self.pk_url_kwarg)
        obj = get_object_or_404(self.model, pk=pk, user=request.user)
        obj.delete()
        return redirect(self.success_url_name)

    def get(self, request, *args, **kwargs):
        return redirect(self.success_url_name)

# Expense Views
class ExpenseListView(TransactionListView):
    model = Expense
    tag_model = ExpenseTag
    category_type = Category.Type.EXPENSE
    list_url_name = "money_app:expenses"
    add_url_name = "money_app:add_expense"
    edit_url_name = "money_app:edit_expense"
    delete_url_name = "money_app:delete_expense"
    transaction_type_label = "Expense"
    transaction_type_plural = "Expenses"

class ExpenseCreateView(TransactionCreateView):
    form_class = ExpenseForm
    success_url_name = "money_app:expenses"
    transaction_type_label = "Expense"
    transaction_type_plural = "Expenses"

class ExpenseUpdateView(TransactionUpdateView):
    model = Expense
    form_class = ExpenseForm
    success_url_name = "money_app:expenses"
    pk_url_kwarg = "expense_id"
    transaction_type_label = "Expense"
    transaction_type_plural = "Expenses"

class ExpenseDeleteView(TransactionDeleteView):
    model = Expense
    success_url_name = "money_app:expenses"
    pk_url_kwarg = "expense_id"

# Income Views
class IncomeListView(TransactionListView):
    model = Income
    tag_model = IncomeTag
    category_type = Category.Type.INCOME
    list_url_name = "money_app:incomes"
    add_url_name = "money_app:add_income"
    edit_url_name = "money_app:edit_income"
    delete_url_name = "money_app:delete_income"
    transaction_type_label = "Income"
    transaction_type_plural = "Incomes"

class IncomeCreateView(TransactionCreateView):
    form_class = IncomeForm
    success_url_name = "money_app:incomes"
    transaction_type_label = "Income"
    transaction_type_plural = "Incomes"

class IncomeUpdateView(TransactionUpdateView):
    model = Income
    form_class = IncomeForm
    success_url_name = "money_app:incomes"
    pk_url_kwarg = "income_id"
    transaction_type_label = "Income"
    transaction_type_plural = "Incomes"

class IncomeDeleteView(TransactionDeleteView):
    model = Income
    success_url_name = "money_app:incomes"
    pk_url_kwarg = "income_id"

# Investment Views
class InvestmentListView(TransactionListView):
    model = Investment
    tag_model = InvestmentTag
    category_type = Category.Type.INVESTMENT
    list_url_name = "money_app:investments"
    add_url_name = "money_app:add_investment"
    edit_url_name = "money_app:edit_investment"
    delete_url_name = "money_app:delete_investment"
    transaction_type_label = "Investment"
    transaction_type_plural = "Investments"

class InvestmentCreateView(TransactionCreateView):
    form_class = InvestmentForm
    success_url_name = "money_app:investments"
    transaction_type_label = "Investment"
    transaction_type_plural = "Investments"

class InvestmentUpdateView(TransactionUpdateView):
    model = Investment
    form_class = InvestmentForm
    success_url_name = "money_app:investments"
    pk_url_kwarg = "investment_id"
    transaction_type_label = "Investment"
    transaction_type_plural = "Investments"

class InvestmentDeleteView(TransactionDeleteView):
    model = Investment
    success_url_name = "money_app:investments"
    pk_url_kwarg = "investment_id"
