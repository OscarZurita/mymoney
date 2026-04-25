from django.urls import path

from . import views

app_name = "money_app"
urlpatterns = [
    path("", views.index, name="index"),
    path("analysis/", views.analysis, name="analysis"),
    path("expenses/new/", views.add_expense, name="add_expense"),
    path("expenses/<int:expense_id>/delete/", views.delete_expense, name="delete_expense"),
    path("signup/", views.signup, name="signup"),
]
