from decimal import Decimal

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from ..models import Debt, Expense, Person, normalize_tag_key, normalize_tag_name


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
        # The person belongs to whoever owns the expense, never to submitted data.
        debt.person, _ = Person.objects.get_or_create(
            user=debt.expense.user,
            normalized_name=normalize_tag_key(name),
            defaults={"name": name},
        )
        debt.set_settled(self.cleaned_data["paid"])
        if commit:
            debt.save()
        return debt


class DebtFormSetBase(BaseInlineFormSet):
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

        # Validating the expense form first sets the amount on the instance.
        expense_amount = self.instance.amount
        if expense_amount is None:
            return

        owed_to_me = owed_by_me = Decimal("0")
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            if form.cleaned_data["direction"] == Debt.Direction.OWED_TO_ME:
                owed_to_me += form.cleaned_data["amount"]
            else:
                owed_by_me += form.cleaned_data["amount"]

        errors = []
        if owed_to_me > expense_amount:
            errors.append("People can't owe you more than the expense amount.")
        if owed_by_me > expense_amount:
            errors.append("You can't owe more than the expense amount.")
        if errors:
            raise forms.ValidationError(errors)


DebtFormSet = inlineformset_factory(
    Expense,
    Debt,
    form=DebtForm,
    formset=DebtFormSetBase,
    extra=0,
    can_delete=True,
)
