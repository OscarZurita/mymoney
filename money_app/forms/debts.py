from decimal import Decimal

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from ..models import (
    Debt,
    Expense,
    Income,
    Person,
    normalize_tag_key,
    normalize_tag_name,
)


class DebtForm(forms.ModelForm):
    person_name = forms.CharField(
        label="Person",
        max_length=Person._meta.get_field("name").max_length,
        widget=forms.TextInput(
            attrs={
                "list": "debt-people",
                "autocomplete": "off",
                "placeholder": "Name",
                "aria-label": "Person",
            }
        ),
    )
    paid = forms.BooleanField(required=False)

    class Meta:
        model = Debt
        fields = ["direction", "person_name", "amount", "paid"]
        widgets = {
            "direction": forms.Select(attrs={"aria-label": "Direction"}),
            "amount": forms.NumberInput(
                attrs={"placeholder": "Amount", "aria-label": "Amount"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial.setdefault("person_name", self.instance.person.name)
            self.initial.setdefault("paid", self.instance.is_settled)

    def clean_person_name(self):
        return normalize_tag_name(self.cleaned_data["person_name"])

    def save(self, commit=True):
        debt = super().save(commit=False)
        name = self.cleaned_data["person_name"]
        # The person belongs to whoever owns the transaction, never to submitted data.
        debt.person, _ = Person.objects.get_or_create(
            user=debt.transaction.user,
            normalized_name=normalize_tag_key(name),
            defaults={"name": name},
        )
        debt.set_settled(self.cleaned_data["paid"])
        if commit:
            debt.save()
        return debt


class IncomeDebtForm(DebtForm):
    class Meta(DebtForm.Meta):
        fields = ["person_name", "amount", "paid"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Someone lent the user this income, so the user is always the one who
        # owes. Leaving the direction off the form keeps it from being changed.
        self.instance.direction = Debt.Direction.OWED_BY_ME


class DebtFormSetBase(BaseInlineFormSet):
    # The legend and help text of the section the formset fills on the form.
    legend = None
    help_text = None

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.people_names = (
            list(Person.objects.filter(user=user).values_list("name", flat=True))
            if user is not None
            else []
        )

    def get_queryset(self):
        return super().get_queryset().select_related("person")

    def clean(self):
        super().clean()
        if any(self.errors):
            return

        # Validating the transaction form first sets the amount on the instance.
        amount = self.instance.amount
        if amount is None:
            return

        owed_to_me = owed_by_me = Decimal("0")
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            # The instance has the direction even when the form has no field for it.
            if form.instance.direction == Debt.Direction.OWED_TO_ME:
                owed_to_me += form.cleaned_data["amount"]
            else:
                owed_by_me += form.cleaned_data["amount"]

        transaction_type = self.instance._meta.verbose_name
        errors = []
        if owed_to_me > amount:
            errors.append(
                f"People can't owe you more than the {transaction_type} amount."
            )
        if owed_by_me > amount:
            errors.append(f"You can't owe more than the {transaction_type} amount.")
        if errors:
            raise forms.ValidationError(errors)


class ExpenseDebtFormSet(
    inlineformset_factory(
        Expense,
        Debt,
        form=DebtForm,
        formset=DebtFormSetBase,
        extra=0,
        can_delete=True,
    )
):
    legend = "Shared with"
    help_text = (
        "Owed by: someone owes you part of what you paid. Owed to: someone paid "
        "this for you. Your statistics count the amount minus what you're owed. "
        "Tick Paid once it's settled."
    )


class IncomeDebtFormSet(
    inlineformset_factory(
        Income,
        Debt,
        form=IncomeDebtForm,
        formset=DebtFormSetBase,
        extra=0,
        can_delete=True,
    )
):
    legend = "Lent by"
    help_text = (
        "Who lent you this money and how much of it you owe them. Your statistics "
        "count the amount minus what you owe. Tick Paid once you've paid it back."
    )
