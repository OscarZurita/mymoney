from django.urls import path

from .views import transactions, views

app_name = "money_app"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("expenses/", views.index, name="expenses"),
    path("add_year_goal", views.add_year_goal, name="add_year_goal"),
    path("year-goals/", views.year_goals, name="year_goals"),
    path("analysis/", views.analysis, name="analysis"),
    path("expenses/new/", views.add_expense, name="add_expense"),
    path("expenses/<int:expense_id>/edit/", views.edit_expense, name="edit_expense"),
    path(
        "expenses/<int:expense_id>/delete/", views.delete_expense, name="delete_expense"
    ),
    # Incomes
    path("incomes/", transactions.IncomeListView.as_view(), name="incomes"),
    path("incomes/new/", transactions.IncomeCreateView.as_view(), name="add_income"),
    path(
        "incomes/<int:income_id>/edit/",
        transactions.IncomeUpdateView.as_view(),
        name="edit_income",
    ),
    path(
        "incomes/<int:income_id>/delete/",
        transactions.IncomeDeleteView.as_view(),
        name="delete_income",
    ),
    # Investments
    path("investments/", transactions.InvestmentListView.as_view(), name="investments"),
    path(
        "investments/new/",
        transactions.InvestmentCreateView.as_view(),
        name="add_investment",
    ),
    path(
        "investments/<int:investment_id>/edit/",
        transactions.InvestmentUpdateView.as_view(),
        name="edit_investment",
    ),
    path(
        "investments/<int:investment_id>/delete/",
        transactions.InvestmentDeleteView.as_view(),
        name="delete_investment",
    ),
    path("signup/", views.signup, name="signup"),
]
