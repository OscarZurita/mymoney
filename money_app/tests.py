import datetime
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import RestrictedError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .formatting import format_money
from .forms import DebtFormSet, ExpenseForm
from .models import (
    Category,
    Debt,
    Expense,
    ExpenseTag,
    Income,
    Investment,
    Person,
    YearGoal,
)


def debt_formset_data(*rows, initial_forms=0):
    """POST data for the debts formset of the expense form, one dict per row."""
    data = {
        "debts-TOTAL_FORMS": str(len(rows)),
        "debts-INITIAL_FORMS": str(initial_forms),
    }
    for index, row in enumerate(rows):
        for field, value in row.items():
            data[f"debts-{index}-{field}"] = value
    return data


class MoneyFormattingTests(TestCase):
    def test_format_money_always_shows_two_decimal_places(self):
        self.assertEqual(format_money(Decimal("19.5")), "19.50")
        self.assertEqual(format_money(Decimal("51.5000000000000")), "51.50")


class TransactionCategoryValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="validator", password="pw")

    def test_transactions_accept_matching_category_type(self):
        for model, category_type in [
            (Expense, Category.Type.EXPENSE),
            (Income, Category.Type.INCOME),
            (Investment, Category.Type.INVESTMENT),
        ]:
            with self.subTest(model=model.__name__):
                category = Category.objects.create(name="Match", type=category_type)
                model(
                    user=self.user, category=category, amount=Decimal("1.00")
                ).full_clean()

    def test_transactions_reject_mismatched_category_type(self):
        for model, category_type in [
            (Expense, Category.Type.INCOME),
            (Income, Category.Type.INVESTMENT),
            (Investment, Category.Type.EXPENSE),
        ]:
            with self.subTest(model=model.__name__):
                category = Category.objects.create(name="Mismatch", type=category_type)
                with self.assertRaises(ValidationError) as ctx:
                    model(
                        user=self.user, category=category, amount=Decimal("1.00")
                    ).full_clean()
                self.assertIn("category", ctx.exception.message_dict)

    def test_clean_without_category_does_not_crash(self):
        for model in (Expense, Income, Investment):
            with self.subTest(model=model.__name__):
                model(user=self.user, amount=Decimal("1.00")).clean()


class DebtModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw")
        self.expense = Expense.objects.create(
            user=self.user,
            amount=Decimal("60.00"),
            category=Category.objects.create(name="Food"),
        )
        self.person = Person.objects.create(user=self.user, name="Bob")

    def test_debt_rejects_a_person_of_another_user(self):
        other_user = User.objects.create_user(username="carol", password="pw")
        stranger = Person.objects.create(user=other_user, name="Bob")

        with self.assertRaises(ValidationError) as ctx:
            Debt(
                expense=self.expense, person=stranger, amount=Decimal("10.00")
            ).full_clean()

        self.assertIn("person", ctx.exception.message_dict)

    def test_debt_amount_must_be_positive(self):
        with self.assertRaises(ValidationError) as ctx:
            Debt(
                expense=self.expense, person=self.person, amount=Decimal("0.00")
            ).full_clean()

        self.assertIn("amount", ctx.exception.message_dict)

    def test_set_settled_keeps_the_first_settlement_date_until_reopened(self):
        debt = Debt(expense=self.expense, person=self.person, amount=Decimal("10.00"))

        debt.set_settled(True)
        self.assertEqual(debt.settled_on, timezone.localdate())

        debt.settled_on = datetime.date(2026, 1, 5)
        debt.set_settled(True)
        self.assertEqual(debt.settled_on, datetime.date(2026, 1, 5))

        debt.set_settled(False)
        self.assertIsNone(debt.settled_on)

    def test_person_with_debts_cannot_be_deleted(self):
        Debt.objects.create(
            expense=self.expense, person=self.person, amount=Decimal("10.00")
        )

        with self.assertRaises(RestrictedError):
            self.person.delete()

    def test_deleting_a_user_deletes_their_people_and_debts(self):
        Debt.objects.create(
            expense=self.expense, person=self.person, amount=Decimal("10.00")
        )

        self.user.delete()

        self.assertFalse(Person.objects.exists())
        self.assertFalse(Debt.objects.exists())


class ExpenseShareTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw")
        self.food = Category.objects.create(name="Food")
        self.bob = Person.objects.create(user=self.user, name="Bob")

    def test_share_of_an_unshared_expense_is_its_amount(self):
        Expense.objects.create(
            user=self.user, amount=Decimal("12.30"), category=self.food
        )

        self.assertEqual(Expense.objects.with_share().get().share, Decimal("12.30"))

    def test_share_subtracts_what_others_owe_whether_paid_back_or_not(self):
        expense = Expense.objects.create(
            user=self.user, amount=Decimal("90.00"), category=self.food
        )
        Debt.objects.create(expense=expense, person=self.bob, amount=Decimal("30.00"))
        Debt.objects.create(
            expense=expense,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("20.00"),
            settled_on=timezone.localdate(),
        )

        self.assertEqual(Expense.objects.with_share().get().share, Decimal("40.00"))

    def test_share_keeps_what_the_user_owes_others(self):
        expense = Expense.objects.create(
            user=self.user, amount=Decimal("14.50"), category=self.food
        )
        Debt.objects.create(
            expense=expense,
            person=self.bob,
            direction=Debt.Direction.OWED_BY_ME,
            amount=Decimal("14.50"),
        )

        self.assertEqual(Expense.objects.with_share().get().share, Decimal("14.50"))


class ExpenseFormTests(TestCase):
    def test_form_accepts_single_category(self):
        food = Category.objects.create(name="Food")

        form = ExpenseForm(
            data={
                "description": "Lunch",
                "date": "2026-04-22",
                "amount": "19.50",
                "category": food.pk,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

        expense = form.save(commit=False)

        self.assertEqual(expense.category, food)

    def test_form_allows_blank_description(self):
        food = Category.objects.create(name="Food")

        form = ExpenseForm(
            data={
                "description": "",
                "date": "2026-04-22",
                "amount": "19.50",
                "category": food.pk,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_form_requires_amount(self):
        food = Category.objects.create(name="Food")

        form = ExpenseForm(
            data={
                "description": "Lunch",
                "date": "2026-04-22",
                "amount": "",
                "category": food.pk,
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("amount", form.errors)

    def test_form_defaults_blank_date_to_current_date(self):
        food = Category.objects.create(name="Food")
        before = timezone.localdate()

        form = ExpenseForm(
            data={
                "description": "Lunch",
                "date": "",
                "amount": "19.50",
                "category": food.pk,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

        expense = form.save(commit=False)
        expense.user = User.objects.create_user(username="alice", password="secret123")
        expense.save()
        after = timezone.localdate()

        self.assertGreaterEqual(expense.date, before)
        self.assertLessEqual(expense.date, after)

    def test_form_requires_category(self):
        form = ExpenseForm(
            data={
                "description": "Lunch",
                "date": "2026-04-22",
                "amount": "19.50",
                "category": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("category", form.errors)

    def test_form_creates_new_tags_once_even_when_casing_differs(self):
        food = Category.objects.create(name="Food")
        user = User.objects.create_user(username="alice", password="secret123")

        form = ExpenseForm(
            data={
                "description": "Lunch",
                "date": "2026-04-22",
                "amount": "19.50",
                "category": food.pk,
                "tags": json.dumps(["Groceries", " groceries ", "Take Away"]),
            },
            user=user,
        )

        self.assertTrue(form.is_valid(), form.errors)

        expense = form.save()

        self.assertEqual(expense.user, user)
        self.assertCountEqual(
            expense.tags.values_list("name", flat=True),
            ["Groceries", "Take Away"],
        )
        self.assertEqual(ExpenseTag.objects.filter(user=user).count(), 2)

    def test_form_reuses_existing_tags_for_the_same_user_case_insensitively(self):
        food = Category.objects.create(name="Food")
        user = User.objects.create_user(username="alice", password="secret123")
        existing_tag = ExpenseTag.objects.create(user=user, name="Coffee")

        form = ExpenseForm(
            data={
                "description": "Morning coffee",
                "date": "2026-04-22",
                "amount": "4.25",
                "category": food.pk,
                "tags": json.dumps(["coffee"]),
            },
            user=user,
        )

        self.assertTrue(form.is_valid(), form.errors)

        expense = form.save()

        self.assertCountEqual(
            expense.tags.values_list("id", flat=True), [existing_tag.id]
        )
        self.assertEqual(ExpenseTag.objects.filter(user=user).count(), 1)

    def test_form_creates_user_specific_tags(self):
        food = Category.objects.create(name="Food")
        user = User.objects.create_user(username="alice", password="secret123")
        other_user = User.objects.create_user(username="bob", password="secret123")
        ExpenseTag.objects.create(user=other_user, name="Coffee")

        form = ExpenseForm(
            data={
                "description": "Coffee run",
                "date": "2026-04-22",
                "amount": "5.00",
                "category": food.pk,
                "tags": json.dumps(["coffee"]),
            },
            user=user,
        )

        self.assertTrue(form.is_valid(), form.errors)

        expense = form.save()

        tag = expense.tags.get()
        self.assertEqual(tag.user, user)
        self.assertEqual(ExpenseTag.objects.filter(normalized_name="coffee").count(), 2)


class DebtFormSetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="pw")
        self.expense = Expense.objects.create(
            user=self.user,
            amount=Decimal("60.00"),
            category=Category.objects.create(name="Food"),
        )

    def formset(self, *rows, initial_forms=0):
        return DebtFormSet(
            debt_formset_data(*rows, initial_forms=initial_forms),
            instance=self.expense,
            user=self.user,
        )

    def test_formset_saves_debts_and_reuses_people_ignoring_case(self):
        Person.objects.create(user=self.user, name="Bob")
        formset = self.formset(
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "bob",
                "amount": "20.00",
            },
            {
                "direction": Debt.Direction.OWED_BY_ME,
                "person_name": "  Carol   Smith ",
                "amount": "5.00",
            },
        )

        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        self.assertEqual(
            list(self.expense.debts.values_list("person__name", "direction", "amount")),
            [
                ("Bob", Debt.Direction.OWED_TO_ME, Decimal("20.00")),
                ("Carol Smith", Debt.Direction.OWED_BY_ME, Decimal("5.00")),
            ],
        )
        self.assertEqual(Person.objects.filter(user=self.user).count(), 2)

    def test_formset_does_not_reuse_another_users_person(self):
        other_user = User.objects.create_user(username="carol", password="pw")
        stranger = Person.objects.create(user=other_user, name="Bob")
        formset = self.formset(
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "Bob",
                "amount": "20.00",
            },
        )

        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        person = self.expense.debts.get().person
        self.assertEqual(person.user, self.user)
        self.assertNotEqual(person, stranger)

    def test_formset_rejects_debts_owed_to_user_above_the_expense_amount(self):
        formset = self.formset(
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "Bob",
                "amount": "40.00",
            },
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "Carol",
                "amount": "30.00",
            },
        )

        self.assertFalse(formset.is_valid())
        self.assertIn(
            "People can't owe you more than the expense amount.",
            formset.non_form_errors(),
        )

    def test_formset_rejects_debts_user_owes_above_the_expense_amount(self):
        formset = self.formset(
            {
                "direction": Debt.Direction.OWED_BY_ME,
                "person_name": "Bob",
                "amount": "60.01",
            },
        )

        self.assertFalse(formset.is_valid())
        self.assertIn(
            "You can't owe more than the expense amount.", formset.non_form_errors()
        )

    def test_formset_ignores_removed_and_blank_rows(self):
        formset = self.formset(
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "Bob",
                "amount": "50.00",
                "DELETE": "on",
            },
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "",
                "amount": "",
            },
            {
                "direction": Debt.Direction.OWED_TO_ME,
                "person_name": "Carol",
                "amount": "30.00",
            },
        )

        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        self.assertEqual(
            list(self.expense.debts.values_list("person__name", flat=True)), ["Carol"]
        )

    def test_paid_checkbox_settles_and_reopens_a_debt(self):
        debt = Debt.objects.create(
            expense=self.expense,
            person=Person.objects.create(user=self.user, name="Bob"),
            amount=Decimal("20.00"),
        )
        row = {
            "id": str(debt.pk),
            "direction": Debt.Direction.OWED_TO_ME,
            "person_name": "Bob",
            "amount": "20.00",
        }

        formset = self.formset({**row, "paid": "on"}, initial_forms=1)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        debt.refresh_from_db()
        self.assertEqual(debt.settled_on, timezone.localdate())

        formset = self.formset(row, initial_forms=1)
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        debt.refresh_from_db()
        self.assertIsNone(debt.settled_on)


class AuthenticatedExpenseViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="secret123")
        self.other_user = User.objects.create_user(username="bob", password="secret123")
        self.food = Category.objects.create(name="Food")
        self.travel = Category.objects.create(name="Travel")

    def test_expenses_requires_login(self):
        response = self.client.get(reverse("money_app:expenses"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('money_app:expenses')}",
        )

    def test_logged_in_user_sees_only_their_expenses(self):
        own_expense = Expense.objects.create(
            user=self.user,
            description="Lunch",
            amount="19.50",
            category=self.food,
        )
        Expense.objects.create(
            user=self.other_user,
            description="Dinner",
            amount="32.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, own_expense.description)
        self.assertNotContains(response, "Dinner")

    def test_expenses_shows_add_expense_link(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "Expense Tracker")
        self.assertContains(response, reverse("money_app:expenses"))
        self.assertContains(response, reverse("money_app:add_expense"))
        self.assertContains(response, "Add new expense")
        self.assertContains(response, "No expenses yet.")

    def test_expenses_shows_expenses_in_table(self):
        Expense.objects.create(
            user=self.user,
            description="Lunch",
            amount="19.50",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "Description")
        self.assertContains(response, "Date")
        self.assertContains(response, "Amount")
        self.assertContains(response, "Category")
        self.assertContains(response, "Tags")
        self.assertContains(response, "Lunch")
        self.assertContains(response, "Filter date")
        self.assertContains(response, "Sort amount")
        self.assertContains(response, "Filter category")
        self.assertContains(response, "Filter tags")

    def test_expenses_formats_expense_amounts_to_two_decimal_places(self):
        Expense.objects.create(
            user=self.user,
            description="Lunch",
            amount=Decimal("19.5"),
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "<td>19.50</td>", html=True)

    def test_expenses_displays_date_without_time(self):
        Expense.objects.create(
            user=self.user,
            description="Coffee",
            date=datetime.date(2026, 4, 22),
            amount="3.50",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "April 22, 2026")
        self.assertNotContains(response, "midnight")

    def test_expenses_filters_by_specific_day(self):
        Expense.objects.create(
            user=self.user,
            description="Lunch",
            date=datetime.date(2026, 4, 22),
            amount="12.00",
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Taxi",
            date=datetime.date(2026, 4, 23),
            amount="25.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:expenses"), {"date": "2026-04-22"}
        )

        self.assertContains(response, "Lunch")
        self.assertNotContains(response, "Taxi")

    def test_expenses_filters_by_month_year_amount_range_and_category(self):
        Expense.objects.create(
            user=self.user,
            description="Train",
            date=datetime.date(2026, 4, 15),
            amount="45.00",
            category=self.travel,
        )
        Expense.objects.create(
            user=self.user,
            description="Breakfast",
            date=datetime.date(2026, 4, 16),
            amount="8.00",
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Flight",
            date=datetime.date(2025, 4, 16),
            amount="200.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:expenses"),
            {
                "month_year": "2026-04",
                "amount_min": "20",
                "amount_max": "100",
                "category": str(self.travel.id),
            },
        )

        self.assertContains(response, "Train")
        self.assertNotContains(response, "Breakfast")
        self.assertNotContains(response, "Flight")

    def test_expenses_filters_by_multiple_tags(self):
        coffee = ExpenseTag.objects.create(user=self.user, name="Coffee")
        weekday = ExpenseTag.objects.create(user=self.user, name="Weekday")
        weekend = ExpenseTag.objects.create(user=self.user, name="Weekend")

        coffee_expense = Expense.objects.create(
            user=self.user,
            description="Cafe stop",
            date=datetime.date(2026, 4, 15),
            amount="4.50",
            category=self.food,
        )
        coffee_expense.tags.add(coffee)

        commute_expense = Expense.objects.create(
            user=self.user,
            description="Morning train",
            date=datetime.date(2026, 4, 15),
            amount="12.00",
            category=self.travel,
        )
        commute_expense.tags.add(weekday)

        brunch_expense = Expense.objects.create(
            user=self.user,
            description="Sunday brunch",
            date=datetime.date(2026, 4, 16),
            amount="18.00",
            category=self.food,
        )
        brunch_expense.tags.add(weekend)

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:expenses"),
            [("tag", str(coffee.id)), ("tag", str(weekend.id))],
        )

        self.assertContains(response, "Cafe stop")
        self.assertContains(response, "Sunday brunch")
        self.assertNotContains(response, "Morning train")

    def test_expenses_month_filter_does_not_match_same_month_other_years(self):
        Expense.objects.create(
            user=self.user,
            description="Hotel 2026",
            date=datetime.date(2026, 5, 10),
            amount="120.00",
            category=self.travel,
        )
        Expense.objects.create(
            user=self.user,
            description="Hotel 2025",
            date=datetime.date(2025, 5, 10),
            amount="110.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:expenses"), {"month_year": "2026-05"}
        )

        self.assertContains(response, "Hotel 2026")
        self.assertNotContains(response, "Hotel 2025")

    def test_expenses_filters_by_min_amount_only(self):
        Expense.objects.create(
            user=self.user,
            description="Cheap snack",
            date=datetime.date(2026, 4, 20),
            amount="4.00",
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Big dinner",
            date=datetime.date(2026, 4, 20),
            amount="40.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"), {"amount_min": "10"})

        self.assertContains(response, "Big dinner")
        self.assertNotContains(response, "Cheap snack")

    def test_expenses_sorts_by_amount_ascending(self):
        Expense.objects.create(
            user=self.user,
            description="Expensive",
            date=datetime.date(2026, 4, 20),
            amount="40.00",
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Cheap",
            date=datetime.date(2026, 4, 20),
            amount="5.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:expenses"), {"sort": "amount_asc"}
        )
        content = response.content.decode()

        self.assertLess(content.index("Cheap"), content.index("Expensive"))

    def test_add_expense_requires_login(self):
        response = self.client.get(reverse("money_app:add_expense"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('money_app:add_expense')}",
        )

    def test_logged_in_user_can_delete_their_own_expense(self):
        expense = Expense.objects.create(
            user=self.user,
            description="Delete me",
            date=datetime.date(2026, 4, 22),
            amount="10.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:delete_expense", args=[expense.id])
        )

        self.assertRedirects(response, reverse("money_app:expenses"))
        self.assertFalse(Expense.objects.filter(id=expense.id).exists())

    def test_user_cannot_delete_another_users_expense(self):
        expense = Expense.objects.create(
            user=self.other_user,
            description="Do not delete",
            date=datetime.date(2026, 4, 22),
            amount="10.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:delete_expense", args=[expense.id])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Expense.objects.filter(id=expense.id).exists())

    def test_dashboard_shows_monthly_goal_progress_from_year_goal(self):
        today = timezone.localdate()
        YearGoal.objects.create(
            user=self.user,
            year=today.year,
            amount=Decimal("1200.00"),
        )
        Expense.objects.create(
            user=self.user,
            description="This month",
            date=today,
            amount=Decimal("25.00"),
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:dashboard"))

        self.assertEqual(response.context["month_total"], Decimal("25.00"))
        self.assertEqual(response.context["monthly_goal"], Decimal("100.00"))
        self.assertEqual(response.context["monthly_goal_percent"], "25")
        self.assertEqual(response.context["monthly_goal_progress_width"], "25")
        self.assertEqual(response.context["ytd_total"], Decimal("25.00"))
        self.assertEqual(response.context["ytd_goal_percent"], "2.08")
        self.assertEqual(response.context["ytd_goal_progress_width"], "2.08")
        self.assertContains(response, "Monthly goal")
        self.assertContains(response, "100.00")
        self.assertContains(response, "25% used")
        self.assertContains(response, "Year goal")
        self.assertContains(response, "1200.00")
        self.assertContains(response, "2.08% used")
        self.assertContains(response, reverse("money_app:add_expense"))
        self.assertContains(response, reverse("money_app:add_year_goal"))

    def test_dashboard_category_table_sums_whole_month_for_current_user(self):
        start_of_month = timezone.localdate().replace(day=1)
        for day, amount in ((0, "10.00"), (1, "15.00")):
            Expense.objects.create(
                user=self.user,
                description="Groceries",
                date=start_of_month + datetime.timedelta(days=day),
                amount=Decimal(amount),
                category=self.food,
            )
        Expense.objects.create(
            user=self.other_user,
            description="Groceries",
            date=start_of_month,
            amount=Decimal("99.00"),
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:dashboard"))

        self.assertEqual(
            response.context["cat_day_rows"],
            [
                {"category": "Food", "total": Decimal("25.00")},
                {"category": "Travel", "total": Decimal("0")},
            ],
        )

    def test_dashboard_counts_only_users_share_of_shared_expenses(self):
        today = timezone.localdate()
        dinner = Expense.objects.create(
            user=self.user,
            description="Dinner",
            date=today,
            amount=Decimal("90.00"),
            category=self.food,
        )
        Debt.objects.create(
            expense=dinner,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("60.00"),
        )
        taxi = Expense.objects.create(
            user=self.user,
            description="Taxi",
            date=today,
            amount=Decimal("15.00"),
            category=self.travel,
        )
        Debt.objects.create(
            expense=taxi,
            person=Person.objects.create(user=self.user, name="Dave"),
            direction=Debt.Direction.OWED_BY_ME,
            amount=Decimal("15.00"),
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:dashboard"))

        self.assertEqual(response.context["month_total"], Decimal("45.00"))
        self.assertEqual(response.context["ytd_total"], Decimal("45.00"))
        self.assertEqual(
            response.context["cat_day_rows"],
            [
                {"category": "Food", "total": Decimal("30.00")},
                {"category": "Travel", "total": Decimal("15.00")},
            ],
        )

    def test_logged_in_user_can_create_year_goal_for_themself(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.post(
            reverse("money_app:add_year_goal"),
            data={
                "year": "2026",
                "amount": "1200.00",
            },
        )

        self.assertRedirects(response, reverse("money_app:dashboard"))
        year_goal = YearGoal.objects.get(year=2026)
        self.assertEqual(year_goal.user, self.user)
        self.assertEqual(year_goal.amount, Decimal("1200.00"))

    def test_add_year_goal_updates_existing_goal_for_same_user_and_year(self):
        existing_goal = YearGoal.objects.create(
            user=self.user,
            year=2026,
            amount=Decimal("1200.00"),
        )
        other_users_goal = YearGoal.objects.create(
            user=self.other_user,
            year=2026,
            amount=Decimal("9999.00"),
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:add_year_goal"),
            data={
                "year": "2026",
                "amount": "2400.00",
            },
        )

        self.assertRedirects(response, reverse("money_app:dashboard"))
        existing_goal.refresh_from_db()
        other_users_goal.refresh_from_db()
        self.assertEqual(existing_goal.amount, Decimal("2400.00"))
        self.assertEqual(other_users_goal.amount, Decimal("9999.00"))
        self.assertEqual(YearGoal.objects.filter(user=self.user, year=2026).count(), 1)

    def test_year_goals_requires_login(self):
        response = self.client.get(reverse("money_app:year_goals"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('money_app:year_goals')}",
        )

    def test_year_goals_show_logged_in_users_goals_with_yearly_expenses(self):
        YearGoal.objects.create(
            user=self.user,
            year=2026,
            amount=Decimal("1200.00"),
        )
        YearGoal.objects.create(
            user=self.user,
            year=2025,
            amount=Decimal("600.00"),
        )
        YearGoal.objects.create(
            user=self.other_user,
            year=2026,
            amount=Decimal("9999.00"),
        )
        Expense.objects.create(
            user=self.user,
            description="Rent",
            date=datetime.date(2026, 1, 10),
            amount=Decimal("200.00"),
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Groceries",
            date=datetime.date(2026, 2, 10),
            amount=Decimal("100.00"),
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Trip",
            date=datetime.date(2025, 6, 10),
            amount=Decimal("700.00"),
            category=self.travel,
        )
        Expense.objects.create(
            user=self.other_user,
            description="Private",
            date=datetime.date(2026, 1, 10),
            amount=Decimal("888.00"),
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:year_goals"))

        goal_rows = response.context["goal_rows"]
        self.assertEqual([row["year"] for row in goal_rows], [2026, 2025])
        self.assertEqual(goal_rows[0]["total_spent"], Decimal("300.00"))
        self.assertEqual(goal_rows[0]["percent"], "25")
        self.assertEqual(goal_rows[0]["progress_width"], "25")
        self.assertEqual(goal_rows[1]["total_spent"], Decimal("700.00"))
        self.assertEqual(goal_rows[1]["percent"], "116.67")
        self.assertEqual(goal_rows[1]["progress_width"], "100")
        self.assertTrue(goal_rows[1]["is_over"])
        self.assertContains(response, "300.00 spent of 1200.00")
        self.assertContains(response, "700.00 spent of 600.00")
        self.assertContains(response, "116.67% used")
        self.assertNotContains(response, "9999.00")
        self.assertNotContains(response, "888.00")

    def test_year_goals_count_only_users_share_of_shared_expenses(self):
        YearGoal.objects.create(user=self.user, year=2026, amount=Decimal("1000.00"))
        trip = Expense.objects.create(
            user=self.user,
            description="Trip",
            date=datetime.date(2026, 3, 1),
            amount=Decimal("300.00"),
            category=self.travel,
        )
        Debt.objects.create(
            expense=trip,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("200.00"),
            settled_on=datetime.date(2026, 3, 10),
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:year_goals"))

        self.assertEqual(
            response.context["goal_rows"][0]["total_spent"], Decimal("100.00")
        )

    def test_analysis_requires_login(self):
        response = self.client.get(reverse("money_app:analysis"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('money_app:analysis')}",
        )

    def test_analysis_shows_only_logged_in_user_data(self):
        Expense.objects.create(
            user=self.user,
            description="Lunch",
            date=datetime.date(2026, 4, 22),
            amount="20.00",
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Taxi",
            date=datetime.date(2026, 4, 23),
            amount="30.00",
            category=self.travel,
        )
        Expense.objects.create(
            user=self.other_user,
            description="Private other user expense",
            date=datetime.date(2026, 4, 24),
            amount="999.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:analysis"))

        self.assertContains(response, "50")
        self.assertContains(response, "Lunch")
        self.assertContains(response, "Taxi")
        self.assertNotContains(response, "Private other user expense")
        self.assertContains(response, "Food")
        self.assertContains(response, "Travel")

    def test_analysis_formats_totals_and_amounts_to_two_decimal_places(self):
        current_year = datetime.datetime.now().year
        YearGoal.objects.create(
            user=self.user,
            year=current_year,
            amount=Decimal("100.0"),
        )
        Expense.objects.create(
            user=self.user,
            description="Lunch",
            date=datetime.date(current_year, 4, 22),
            amount=Decimal("19.5"),
            category=self.food,
        )
        Expense.objects.create(
            user=self.user,
            description="Dinner",
            date=datetime.date(current_year, 4, 23),
            amount=Decimal("32.125"),
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:analysis"))

        self.assertContains(response, "51.63/100.00")
        self.assertContains(response, "Monthly expense totals")
        self.assertContains(response, "51.63")
        self.assertContains(response, "32.13")
        self.assertContains(response, "62.23%")

    def test_analysis_counts_only_users_share_of_shared_expenses(self):
        dinner = Expense.objects.create(
            user=self.user,
            description="Dinner",
            date=datetime.date(2026, 4, 22),
            amount=Decimal("90.00"),
            category=self.food,
        )
        Debt.objects.create(
            expense=dinner,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("60.00"),
        )
        Expense.objects.create(
            user=self.user,
            description="Taxi",
            date=datetime.date(2026, 4, 23),
            amount=Decimal("40.00"),
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:analysis"), {"year": "2026"})

        summary = response.context["summary"]
        self.assertEqual(summary["total_spent"], Decimal("70.00"))
        self.assertEqual(summary["average_expense"], Decimal("35.00"))
        self.assertEqual(summary["highest_expense"], Decimal("40.00"))
        self.assertEqual(
            [row["total"] for row in response.context["monthly_totals"]],
            [Decimal("70.00")],
        )
        self.assertEqual(
            [
                (row["category__name"], row["total"])
                for row in response.context["category_breakdown"]
            ],
            [("Travel", Decimal("40.00")), ("Food", Decimal("30.00"))],
        )
        self.assertEqual(
            [
                (expense.description, expense.share)
                for expense in response.context["largest_expenses"]
            ],
            [("Taxi", Decimal("40.00")), ("Dinner", Decimal("30.00"))],
        )

    def test_analysis_can_be_filtered_by_year(self):
        Expense.objects.create(
            user=self.user,
            description="Trip 2026",
            date=datetime.date(2026, 5, 10),
            amount="80.00",
            category=self.travel,
        )
        Expense.objects.create(
            user=self.user,
            description="Trip 2025",
            date=datetime.date(2025, 5, 10),
            amount="40.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:analysis"), {"year": "2026"})

        self.assertContains(response, "Trip 2026")
        self.assertNotContains(response, "Trip 2025")
        self.assertContains(response, "80")

    def test_analysis_defaults_to_current_year_but_all_years_can_be_selected(self):
        current_year = timezone.localdate().year
        previous_year = current_year - 1
        Expense.objects.create(
            user=self.user,
            description="Current year expense",
            date=datetime.date(current_year, 5, 10),
            amount="80.00",
            category=self.travel,
        )
        Expense.objects.create(
            user=self.user,
            description="Previous year expense",
            date=datetime.date(previous_year, 5, 10),
            amount="40.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:analysis"))

        self.assertEqual(response.context["selected_year"], str(current_year))
        self.assertContains(response, "Current year expense")
        self.assertNotContains(response, "Previous year expense")

        response = self.client.get(reverse("money_app:analysis"), {"year": ""})

        self.assertEqual(response.context["selected_year"], "")
        self.assertContains(response, "Current year expense")
        self.assertContains(response, "Previous year expense")

    def test_logged_in_user_creates_expense_for_themself(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.post(
            reverse("money_app:add_expense"),
            data={
                "description": "Groceries",
                "date": "2026-04-22",
                "amount": "49.95",
                "category": self.food.pk,
                **debt_formset_data(),
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))
        expense = Expense.objects.get(description="Groceries")
        self.assertEqual(expense.user, self.user)
        self.assertEqual(expense.date, datetime.date(2026, 4, 22))

    def test_add_expense_page_shows_tag_input(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:add_expense"))

        self.assertContains(response, "Tags")
        self.assertContains(response, "expense-tag-input")

    def test_logged_in_user_can_create_expense_with_existing_and_new_tags(self):
        ExpenseTag.objects.create(user=self.user, name="Coffee")

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:add_expense"),
            data={
                "description": "Brunch",
                "date": "2026-04-22",
                "amount": "21.50",
                "category": self.food.pk,
                "tags": json.dumps(["coffee", "Weekend"]),
                **debt_formset_data(),
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))

        expense = Expense.objects.get(description="Brunch")
        self.assertCountEqual(
            expense.tags.values_list("name", flat=True),
            ["Coffee", "Weekend"],
        )
        self.assertEqual(ExpenseTag.objects.filter(user=self.user).count(), 2)

    def test_logged_in_user_can_update_expense_tags(self):
        expense = Expense.objects.create(
            user=self.user,
            description="Lunch",
            date=datetime.date(2026, 4, 22),
            amount="19.50",
            category=self.food,
        )
        expense.tags.add(ExpenseTag.objects.create(user=self.user, name="Weekday"))
        ExpenseTag.objects.create(user=self.user, name="Coffee")

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:edit_expense", args=[expense.id]),
            data={
                "description": "Lunch",
                "date": "2026-04-22",
                "amount": "19.50",
                "category": self.food.pk,
                "tags": json.dumps(["coffee"]),
                **debt_formset_data(),
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))

        expense.refresh_from_db()
        self.assertCountEqual(expense.tags.values_list("name", flat=True), ["Coffee"])

    def test_add_expense_page_shows_shared_with_section(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:add_expense"))

        self.assertContains(response, "Shared with")
        self.assertContains(response, 'id="debt-row-template"')

    def test_logged_in_user_can_create_expense_shared_with_people(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.post(
            reverse("money_app:add_expense"),
            data={
                "description": "Dinner",
                "date": "2026-04-22",
                "amount": "60.00",
                "category": self.food.pk,
                **debt_formset_data(
                    {
                        "direction": Debt.Direction.OWED_TO_ME,
                        "person_name": "Carol",
                        "amount": "20.00",
                    },
                    {
                        "direction": Debt.Direction.OWED_TO_ME,
                        "person_name": "Dave",
                        "amount": "20.00",
                        "paid": "on",
                    },
                ),
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))
        expense = Expense.objects.get(description="Dinner")
        self.assertEqual(
            [
                (debt.person.name, debt.person.user, debt.amount, debt.is_settled)
                for debt in expense.debts.all()
            ],
            [
                ("Carol", self.user, Decimal("20.00"), False),
                ("Dave", self.user, Decimal("20.00"), True),
            ],
        )

    def test_add_expense_with_too_large_debts_saves_nothing(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.post(
            reverse("money_app:add_expense"),
            data={
                "description": "Dinner",
                "date": "2026-04-22",
                "amount": "60.00",
                "category": self.food.pk,
                **debt_formset_data(
                    {
                        "direction": Debt.Direction.OWED_TO_ME,
                        "person_name": "Carol",
                        "amount": "80.00",
                    },
                ),
            },
        )

        self.assertContains(
            response, "People can&#x27;t owe you more than the expense amount."
        )
        self.assertFalse(Expense.objects.filter(description="Dinner").exists())
        self.assertFalse(Person.objects.exists())

    def test_edit_expense_page_shows_its_debts_and_only_the_users_people(self):
        expense = Expense.objects.create(
            user=self.user,
            description="Dinner",
            amount=Decimal("60.00"),
            category=self.food,
        )
        Debt.objects.create(
            expense=expense,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("20.00"),
        )
        Person.objects.create(user=self.other_user, name="Mallory")

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:edit_expense", args=[expense.id]))

        self.assertContains(response, 'value="Carol"')
        self.assertContains(response, 'value="20.00"')
        self.assertNotContains(response, "Mallory")

    def test_user_cannot_change_another_users_debt_through_their_expense(self):
        own_expense = Expense.objects.create(
            user=self.user,
            description="Lunch",
            amount=Decimal("20.00"),
            category=self.food,
        )
        other_debt = Debt.objects.create(
            expense=Expense.objects.create(
                user=self.other_user,
                description="Dinner",
                amount=Decimal("50.00"),
                category=self.food,
            ),
            person=Person.objects.create(user=self.other_user, name="Mallory"),
            amount=Decimal("25.00"),
        )
        row = {
            "id": str(other_debt.pk),
            "direction": Debt.Direction.OWED_TO_ME,
            "person_name": "Mallory",
            "amount": "1.00",
            "paid": "on",
        }
        expense_data = {
            "description": "Lunch",
            "date": "2026-04-22",
            "amount": "20.00",
            "category": self.food.pk,
        }

        self.client.login(username="alice", password="secret123")
        for tampered_row in (row, {**row, "DELETE": "on"}):
            with self.subTest(delete="DELETE" in tampered_row):
                self.client.post(
                    reverse("money_app:edit_expense", args=[own_expense.id]),
                    data={
                        **expense_data,
                        **debt_formset_data(tampered_row, initial_forms=1),
                    },
                )

                other_debt.refresh_from_db()
                self.assertEqual(other_debt.expense.user, self.other_user)
                self.assertEqual(other_debt.amount, Decimal("25.00"))
                self.assertIsNone(other_debt.settled_on)
                self.assertFalse(own_expense.debts.exists())

    def test_expenses_list_shows_who_owes_what(self):
        expense = Expense.objects.create(
            user=self.user,
            description="Dinner",
            amount=Decimal("60.00"),
            category=self.food,
        )
        Debt.objects.create(
            expense=expense,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("20.00"),
        )
        Debt.objects.create(
            expense=expense,
            person=Person.objects.create(user=self.user, name="Dave"),
            direction=Debt.Direction.OWED_BY_ME,
            amount=Decimal("5.00"),
            settled_on=timezone.localdate(),
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "Owed by Carol 20.00")
        self.assertContains(response, "Owed to Dave 5.00 (paid)")

    def test_expenses_list_shows_users_share_of_shared_expenses(self):
        dinner = Expense.objects.create(
            user=self.user,
            description="Dinner",
            amount=Decimal("60.00"),
            category=self.food,
        )
        Debt.objects.create(
            expense=dinner,
            person=Person.objects.create(user=self.user, name="Carol"),
            amount=Decimal("20.00"),
        )
        Expense.objects.create(
            user=self.user,
            description="Solo lunch",
            amount=Decimal("12.00"),
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "Your share 40.00", count=1)
        self.assertContains(response, "Your share", count=1)

    def test_expenses_does_not_show_category_creation_ui(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:expenses"))

        self.assertNotContains(response, "Add a category")
        self.assertNotContains(response, "Available categories")
        self.assertNotContains(response, "Save category")


class AuthenticatedDebtViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="secret123")
        self.other_user = User.objects.create_user(username="bob", password="secret123")
        self.food = Category.objects.create(name="Food")

    def create_debt(
        self,
        user,
        person_name,
        amount,
        direction=Debt.Direction.OWED_TO_ME,
        settled_on=None,
        description="Dinner",
        date=None,
        category=None,
    ):
        person, _ = Person.objects.get_or_create(
            user=user,
            normalized_name=person_name.casefold(),
            defaults={"name": person_name},
        )
        expense = Expense.objects.create(
            user=user,
            description=description,
            date=date or timezone.localdate(),
            amount=Decimal("100.00"),
            category=category or self.food,
        )
        return Debt.objects.create(
            expense=expense,
            person=person,
            direction=direction,
            amount=Decimal(amount),
            settled_on=settled_on,
        )

    def test_debt_views_require_login(self):
        debt = self.create_debt(self.user, "Carol", "30.00")

        for url, method in (
            (reverse("money_app:debts"), self.client.get),
            (reverse("money_app:settle_debt", args=[debt.id]), self.client.post),
            (reverse("money_app:reopen_debt", args=[debt.id]), self.client.post),
        ):
            with self.subTest(url=url):
                self.assertRedirects(method(url), f"{reverse('login')}?next={url}")

    def test_navigation_links_to_debts(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:dashboard"))

        self.assertContains(response, reverse("money_app:debts"))

    def test_debts_shows_totals_and_balances_of_the_users_open_debts(self):
        self.create_debt(self.user, "Carol", "30.00")
        self.create_debt(
            self.user, "Carol", "10.00", direction=Debt.Direction.OWED_BY_ME
        )
        self.create_debt(
            self.user, "Dave", "14.50", direction=Debt.Direction.OWED_BY_ME
        )
        self.create_debt(self.user, "Erin", "5.00", settled_on=timezone.localdate())
        self.create_debt(self.other_user, "Mallory", "99.00", description="Secret")

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:debts"))

        self.assertEqual(
            response.context["totals"],
            {"owed_to_me": Decimal("30.00"), "owed_by_me": Decimal("24.50")},
        )
        self.assertEqual(
            [
                (row["person__name"], row["net"], row["they_owe_me"])
                for row in response.context["balances"]
            ],
            [("Carol", Decimal("20.00"), True), ("Dave", Decimal("14.50"), False)],
        )
        self.assertEqual(
            [debt.person.name for debt in response.context["recently_settled"]],
            ["Erin"],
        )
        self.assertContains(response, "Carol owes you")
        self.assertContains(response, "You owe Dave")
        self.assertContains(response, "Erin paid you")
        self.assertNotContains(response, "Mallory")
        self.assertNotContains(response, "Secret")

    def test_user_can_settle_and_reopen_their_debt(self):
        debt = self.create_debt(self.user, "Carol", "30.00")
        self.client.login(username="alice", password="secret123")

        response = self.client.post(reverse("money_app:settle_debt", args=[debt.id]))

        self.assertRedirects(response, reverse("money_app:debts"))
        debt.refresh_from_db()
        self.assertEqual(debt.settled_on, timezone.localdate())

        response = self.client.post(reverse("money_app:reopen_debt", args=[debt.id]))

        self.assertRedirects(response, reverse("money_app:debts"))
        debt.refresh_from_db()
        self.assertIsNone(debt.settled_on)

    def test_user_cannot_settle_or_reopen_another_users_debt(self):
        open_debt = self.create_debt(self.other_user, "Mallory", "30.00")
        settled_debt = self.create_debt(
            self.other_user, "Mallory", "10.00", settled_on=datetime.date(2026, 1, 5)
        )
        self.client.login(username="alice", password="secret123")

        for url_name, debt in (
            ("money_app:settle_debt", open_debt),
            ("money_app:reopen_debt", settled_debt),
        ):
            with self.subTest(url_name=url_name):
                response = self.client.post(reverse(url_name, args=[debt.id]))
                self.assertEqual(response.status_code, 404)

        open_debt.refresh_from_db()
        settled_debt.refresh_from_db()
        self.assertIsNone(open_debt.settled_on)
        self.assertEqual(settled_debt.settled_on, datetime.date(2026, 1, 5))

    def test_settle_debt_get_does_not_change_it(self):
        debt = self.create_debt(self.user, "Carol", "30.00")
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:settle_debt", args=[debt.id]))

        self.assertRedirects(response, reverse("money_app:debts"))
        debt.refresh_from_db()
        self.assertIsNone(debt.settled_on)

    def test_settling_a_debt_does_not_change_spending_totals(self):
        debt = self.create_debt(self.user, "Carol", "30.00")
        self.client.login(username="alice", password="secret123")

        before = self.client.get(reverse("money_app:dashboard"))
        self.client.post(reverse("money_app:settle_debt", args=[debt.id]))
        after = self.client.get(reverse("money_app:dashboard"))

        self.assertEqual(before.context["month_total"], Decimal("70.00"))
        self.assertEqual(after.context["month_total"], Decimal("70.00"))

    def test_debts_page_without_debts_shows_no_filters(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:debts"))

        self.assertContains(response, "No open debts.")
        self.assertNotContains(response, 'class="filter-bar"')

    def test_debts_filters_both_lists_by_person_and_direction_but_not_totals(self):
        self.create_debt(self.user, "Carol", "30.00", description="Carol open")
        self.create_debt(
            self.user,
            "Carol",
            "8.00",
            direction=Debt.Direction.OWED_BY_ME,
            description="Carol lent",
        )
        self.create_debt(
            self.user,
            "Carol",
            "12.00",
            settled_on=datetime.date(2026, 5, 2),
            description="Carol settled",
        )
        self.create_debt(self.user, "Dave", "50.00", description="Dave open")
        self.create_debt(
            self.user,
            "Dave",
            "20.00",
            settled_on=datetime.date(2026, 6, 1),
            description="Dave settled",
        )
        carol = Person.objects.get(user=self.user, name="Carol")

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:debts"),
            {"person": [carol.id], "direction": Debt.Direction.OWED_TO_ME},
        )

        self.assertEqual(
            [debt.expense.description for debt in response.context["open_debts"]],
            ["Carol open"],
        )
        self.assertEqual(
            [debt.expense.description for debt in response.context["recently_settled"]],
            ["Carol settled"],
        )
        self.assertEqual(
            response.context["totals"],
            {"owed_to_me": Decimal("80.00"), "owed_by_me": Decimal("8.00")},
        )
        self.assertEqual(
            [row["person__name"] for row in response.context["balances"]],
            ["Carol", "Dave"],
        )
        self.assertContains(response, "Clear filters")

    def test_debts_filters_by_expense_date_amount_and_category(self):
        travel = Category.objects.create(name="Travel")
        self.create_debt(
            self.user,
            "Carol",
            "30.00",
            date=datetime.date(2026, 3, 14),
            description="March dinner",
        )
        self.create_debt(
            self.user,
            "Carol",
            "5.00",
            date=datetime.date(2026, 3, 20),
            description="March coffee",
        )
        self.create_debt(
            self.user,
            "Carol",
            "40.00",
            date=datetime.date(2026, 3, 22),
            category=travel,
            description="March train",
        )
        self.create_debt(
            self.user,
            "Carol",
            "35.00",
            date=datetime.date(2025, 3, 14),
            description="Last year's dinner",
        )

        self.client.login(username="alice", password="secret123")
        for params, expected in (
            ({"date": "2026-03-14"}, ["March dinner"]),
            (
                {"month_year": "2026-03", "amount_min": "10"},
                ["March train", "March dinner"],
            ),
            ({"year": "2026", "amount_max": "10"}, ["March coffee"]),
            (
                {"year": "2026", "category": str(self.food.id)},
                ["March coffee", "March dinner"],
            ),
        ):
            with self.subTest(params=params):
                response = self.client.get(reverse("money_app:debts"), params)

                self.assertEqual(
                    [
                        debt.expense.description
                        for debt in response.context["open_debts"]
                    ],
                    expected,
                )

    def test_debts_ignores_invalid_filters_and_other_users_people(self):
        self.create_debt(self.user, "Carol", "30.00")
        stranger = Person.objects.create(user=self.other_user, name="Mallory")

        self.client.login(username="alice", password="secret123")
        response = self.client.get(
            reverse("money_app:debts"),
            {
                "date": "2026-02-30",
                "month_year": "0000-01",
                "year": "0",
                "person": [str(stranger.id), "abc"],
                "direction": "sideways",
                "amount_min": "Infinity",
                "amount_max": "lots",
                "category": "999999",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_active_filters"])
        self.assertEqual(len(response.context["open_debts"]), 1)
        self.assertNotContains(response, "Mallory")

    def test_recently_settled_shows_the_20_latest_matching_debts(self):
        for day in range(1, 26):
            self.create_debt(
                self.user,
                "Carol",
                "1.00",
                settled_on=datetime.date(2026, 1, day),
                description=f"Carol {day}",
            )
        self.create_debt(
            self.user,
            "Dave",
            "1.00",
            settled_on=datetime.date(2026, 2, 1),
            description="Dave",
        )
        carol = Person.objects.get(user=self.user, name="Carol")

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:debts"))

        settled = [
            debt.expense.description for debt in response.context["recently_settled"]
        ]
        self.assertEqual(settled[:2], ["Dave", "Carol 25"])
        self.assertEqual(len(settled), 20)
        self.assertContains(response, "The 20 most recent of 26.")

        response = self.client.get(reverse("money_app:debts"), {"person": [carol.id]})

        self.assertEqual(
            [debt.expense.description for debt in response.context["recently_settled"]],
            [f"Carol {day}" for day in range(25, 5, -1)],
        )
        self.assertContains(response, "The 20 most recent of 25.")


class AuthenticatedIncomeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="secret123")
        self.salary = Category.objects.create(name="Salary", type=Category.Type.INCOME)

    def test_logged_in_user_creates_income_for_themself(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.post(
            reverse("money_app:add_income"),
            data={
                "description": "October salary",
                "date": "2026-10-01",
                "amount": "1500.00",
                "category": self.salary.pk,
            },
        )

        self.assertRedirects(response, reverse("money_app:incomes"))
        self.assertEqual(Income.objects.get().user, self.user)


class SignUpViewTests(TestCase):
    def test_user_can_sign_up(self):
        response = self.client.post(
            reverse("money_app:signup"),
            data={
                "username": "charlie",
                "password1": "super-secret-pass123",
                "password2": "super-secret-pass123",
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))
        self.assertTrue(User.objects.filter(username="charlie").exists())
