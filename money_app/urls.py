from django.urls import path

from . import views

app_name = "money_app"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("expenses/", views.index, name="expenses"),
    path("add_year_goal", views.add_year_goal, name = "add_year_goal"),
    path("year-goals/", views.year_goals, name="year_goals"),
    path("analysis/", views.analysis, name="analysis"),
    path("expenses/new/", views.add_expense, name="add_expense"),
    path("expenses/<int:expense_id>/edit/", views.edit_expense, name="edit_expense"),
    path("expenses/<int:expense_id>/delete/", views.delete_expense, name="delete_expense"),
    path("signup/", views.signup, name="signup"),
]
