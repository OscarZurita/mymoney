import json
from django import forms
from django.utils import timezone
from ..models import normalize_tag_key, normalize_tag_name, Category, Expense, Income, Investment, ExpenseTag, IncomeTag, InvestmentTag

class TransactionFormBase(forms.ModelForm):
    tag_model = None
    category_type = None

    tags = forms.CharField(required=False, widget=forms.HiddenInput())
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        fields = ["description", "date", "amount", "category", "tags"]

    def __init__(self, *args, user=None, **kwargs):
        if self.tag_model is None or self.category_type is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must define 'tag_model' and 'category_type'."
            )

        self.user = user
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = Category.objects.filter(
            type=self.category_type
        )

        user = self.user or getattr(self.instance, "user", None)
        if user is not None and getattr(user, "pk", None):
            self.available_tags = list(
                self.tag_model.objects.filter(user=user)
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

        max_length = self.tag_model._meta.get_field("name").max_length
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

    def _save_tags(self, transaction):
        tag_names = self.cleaned_data.get("tags", [])

        if transaction.pk is None:
            raise ValueError(
                f"{transaction.__class__.__name__} must be saved before tags can be assigned."
            )
        if tag_names and transaction.user_id is None:
            raise ValueError(
                f"{transaction.__class__.__name__} must have a user before tags can be assigned."
            )

        tags = []
        if tag_names:
            tag_keys = [normalize_tag_key(name) for name in tag_names]
            existing_tags = {
                tag.normalized_name: tag
                for tag in self.tag_model.objects.filter(
                    user=transaction.user,
                    normalized_name__in=tag_keys,
                )
            }

            for tag_name in tag_names:
                tag_key = normalize_tag_key(tag_name)
                tag = existing_tags.get(tag_key)
                if tag is None:
                    tag = self.tag_model.objects.create(
                        user=transaction.user, name=tag_name
                    )
                    existing_tags[tag_key] = tag
                tags.append(tag)

        transaction.tags.set(tags)

    def save(self, commit=True):
        transaction = super().save(commit=False)
        if transaction.date is None:
            transaction.date = timezone.localdate()
        if self.user is not None and transaction.user_id is None:
            transaction.user = self.user
        if commit:
            transaction.save()
            self._save_tags(transaction)
        else:
            self.save_m2m = lambda: self._save_tags(transaction)
        return transaction
    
class ExpenseForm(TransactionFormBase):
    tag_model = ExpenseTag
    category_type = Category.Type.EXPENSE

    class Meta(TransactionFormBase.Meta):
        model = Expense


class IncomeForm(TransactionFormBase):
    tag_model = IncomeTag
    category_type = Category.Type.INCOME

    class Meta(TransactionFormBase.Meta):
        model = Income


class InvestmentForm(TransactionFormBase):
    tag_model = InvestmentTag
    category_type = Category.Type.INVESTMENT

    class Meta(TransactionFormBase.Meta):
        model = Investment