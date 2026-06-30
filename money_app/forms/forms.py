import json

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from ..models import Category, YearGoal

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]


class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)

class YearGoalForm(forms.ModelForm):
    class Meta:
        model = YearGoal
        fields = ["year", "amount"]
        
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        if not self.is_bound and self.user is not None and not self.instance.pk:
            current_year = timezone.localdate().year
            current_goal = YearGoal.objects.filter(
                user=self.user,
                year=current_year,
            ).first()

            if current_goal is not None:
                self.instance = current_goal
                self.initial.setdefault("year", current_goal.year)
                self.initial.setdefault("amount", current_goal.amount)
            else:
                self.initial.setdefault("year", current_year)

    def save(self, commit=True):
        year_goal = super().save(commit=False)

        if self.user is not None:
            existing_goal = YearGoal.objects.filter(
                user=self.user,
                year=year_goal.year,
            ).first()

            if existing_goal is not None and existing_goal.pk != year_goal.pk:
                year_goal = existing_goal
                year_goal.amount = self.cleaned_data["amount"]
            else:
                year_goal.user = self.user

        if commit:
            year_goal.save()

        return year_goal
