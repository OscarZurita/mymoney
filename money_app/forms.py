import json

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Category, Expense, Income, Tag, YearGoal, normalize_tag_key, normalize_tag_name


class ExpenseForm(forms.ModelForm):
    tags = forms.CharField(required=False, widget=forms.HiddenInput())
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = Expense
        fields = ["description", "date", "amount", "category", "tags"]

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        owner = self.user or getattr(self.instance, "owner", None)
        if owner is not None and getattr(owner, "pk", None):
            self.available_tags = list(
                Tag.objects.filter(owner=owner)
                .order_by("name")
                .values_list("name", flat=True)
            )
        else:
            self.available_tags = []

        if not self.is_bound:
            selected_tags = []
            if self.instance.pk:
                selected_tags = list(
                    self.instance.tags.order_by("name").values_list("name", flat=True)
                )
            self.fields["tags"].initial = json.dumps(selected_tags)

    def clean_tags(self):
        raw_tags = self.cleaned_data.get("tags", "")
        parsed_tags = []

        if isinstance(raw_tags, (list, tuple)):
            parsed_tags = list(raw_tags)
        elif raw_tags:
            try:
                parsed_tags = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                parsed_tags = raw_tags.split(",")

        if isinstance(parsed_tags, str):
            parsed_tags = [parsed_tags]

        if not isinstance(parsed_tags, list):
            raise forms.ValidationError("Tags must be a list.")

        max_length = Tag._meta.get_field("name").max_length
        cleaned_tags = []
        seen_keys = set()

        for value in parsed_tags:
            if not isinstance(value, str):
                continue

            tag_name = normalize_tag_name(value)
            if not tag_name:
                continue
            if len(tag_name) > max_length:
                raise forms.ValidationError(
                    f"Each tag must be {max_length} characters or fewer."
                )

            tag_key = normalize_tag_key(tag_name)
            if tag_key in seen_keys:
                continue

            seen_keys.add(tag_key)
            cleaned_tags.append(tag_name)

        return cleaned_tags

    def _save_tags(self, expense):
        tag_names = self.cleaned_data.get("tags", [])

        if expense.pk is None:
            raise ValueError("Expense must be saved before tags can be assigned.")
        if tag_names and expense.owner_id is None:
            raise ValueError("Expense must have an owner before tags can be assigned.")

        tags = []
        if tag_names:
            tag_keys = [normalize_tag_key(name) for name in tag_names]
            existing_tags = {
                tag.normalized_name: tag
                for tag in Tag.objects.filter(
                    owner=expense.owner,
                    normalized_name__in=tag_keys,
                )
            }

            for tag_name in tag_names:
                tag_key = normalize_tag_key(tag_name)
                tag = existing_tags.get(tag_key)
                if tag is None:
                    tag = Tag.objects.create(owner=expense.owner, name=tag_name)
                    existing_tags[tag_key] = tag
                tags.append(tag)

        expense.tags.set(tags)

    def save(self, commit=True):
        expense = super().save(commit=False)
        if expense.date is None:
            expense.date = timezone.localdate()
        if self.user is not None and expense.owner_id is None:
            expense.owner = self.user
        if commit:
            expense.save()
            self._save_tags(expense)
        else:
            self.save_m2m = lambda: self._save_tags(expense)
        return expense

class IncomeForm(forms.ModelForm):
    class Meta:
        model = Income
        fields = ["description", "date", "amount", "tags"]

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
