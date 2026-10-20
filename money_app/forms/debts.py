from decimal import Decimal

from django import forms
from django.db.models import Sum
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from ..formatting import format_money
from ..models import (
    Debt,
    Expense,
    Income,
    Person,
    Repayment,
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

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get("amount")
        if amount is None or self.instance.pk is None:
            return cleaned_data

        kept = self.instance.repayments.aggregate(
            total=Sum("amount", default=Decimal("0"))
        )["total"]
        if self.initial.get("paid"):
            # Saving undoes or redoes the repayment that settled the debt (see
            # _save_repayments), so only the earlier ones stay.
            kept -= self.instance.repayments.latest().amount
        if amount < kept:
            self.add_error(
                "amount",
                f"Can't be less than the {format_money(kept)} already paid back.",
            )
        return cleaned_data

    def save(self, commit=True):
        debt = super().save(commit=False)
        name = self.cleaned_data["person_name"]
        # The person belongs to whoever owns the transaction, never to submitted data.
        debt.person, _ = Person.objects.get_or_create(
            user=debt.transaction.user,
            normalized_name=normalize_tag_key(name),
            defaults={"name": name},
        )
        if commit:
            debt.save()
            self._save_repayments(debt)
        else:
            self.save_m2m = lambda: self._save_repayments(debt)
        return debt

    def _save_repayments(self, debt):
        date = None
        if self.initial.get("paid"):
            # The latest repayment settled the debt. Undo it, and when Paid stays
            # ticked, repay the rest on its date, so that the debt stays settled
            # if its amount changed.
            date = debt.reopen().date
        if self.cleaned_data["paid"]:
            debt.pay_off(date)
        # The repayments may cover a lowered amount already.
        debt.update_settled_on()


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
        return super().get_queryset().select_related("person").with_repaid()

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
        "Tick Paid once it's settled. To pay in installments, add payments from "
        "the Debts page."
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
        "count the amount minus what you owe. Tick Paid once you've paid it back. "
        "To pay in installments, add payments from the Debts page."
    )


class RepaymentForm(forms.ModelForm):
    date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
        input_formats=["%Y-%m-%d"],
    )

    class Meta:
        model = Repayment
        fields = ["amount", "date"]

    def __init__(self, *args, debt, **kwargs):
        super().__init__(*args, **kwargs)
        # The view finds the debt among the user's, never from submitted data.
        self.instance.debt = debt
        # The debt comes from Debt.objects.with_repaid(), so it knows what's left.
        self.fields["amount"].widget.attrs["placeholder"] = format_money(debt.remaining)
