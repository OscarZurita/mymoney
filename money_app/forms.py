from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Category, Expense


class ExpenseForm(forms.ModelForm):
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = Expense
        fields = ["description", "date", "amount", "category"]

    def save(self, commit=True):
        expense = super().save(commit=False)
        if expense.date is None:
            expense.date = timezone.localdate()
        if commit:
            expense.save()
        return expense


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)
