import json
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ExpenseForm
from .formatting import format_money
from .models import Category, Expense, Tag, YearGoal


class MoneyFormattingTests(TestCase):
    def test_format_money_always_shows_two_decimal_places(self):
        self.assertEqual(format_money(Decimal("19.5")), "19.50")
        self.assertEqual(format_money(Decimal("51.5000000000000")), "51.50")


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
        expense.owner = User.objects.create_user(username="alice", password="secret123")
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

        self.assertEqual(expense.owner, user)
        self.assertCountEqual(
            expense.tags.values_list("name", flat=True),
            ["Groceries", "Take Away"],
        )
        self.assertEqual(Tag.objects.filter(owner=user).count(), 2)

    def test_form_reuses_existing_tags_for_the_same_user_case_insensitively(self):
        food = Category.objects.create(name="Food")
        user = User.objects.create_user(username="alice", password="secret123")
        existing_tag = Tag.objects.create(owner=user, name="Coffee")

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

        self.assertCountEqual(expense.tags.values_list("id", flat=True), [existing_tag.id])
        self.assertEqual(Tag.objects.filter(owner=user).count(), 1)

    def test_form_creates_user_specific_tags(self):
        food = Category.objects.create(name="Food")
        user = User.objects.create_user(username="alice", password="secret123")
        other_user = User.objects.create_user(username="bob", password="secret123")
        Tag.objects.create(owner=other_user, name="Coffee")

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
        self.assertEqual(tag.owner, user)
        self.assertEqual(Tag.objects.filter(normalized_name="coffee").count(), 2)


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
            owner=self.user,
            description="Lunch",
            amount="19.50",
            category=self.food,
        )
        Expense.objects.create(
            owner=self.other_user,
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
            owner=self.user,
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
            owner=self.user,
            description="Lunch",
            amount=Decimal("19.5"),
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"))

        self.assertContains(response, "<td>19.50</td>", html=True)

    def test_expenses_displays_date_without_time(self):
        Expense.objects.create(
            owner=self.user,
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
            owner=self.user,
            description="Lunch",
            date=datetime.date(2026, 4, 22),
            amount="12.00",
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
            description="Taxi",
            date=datetime.date(2026, 4, 23),
            amount="25.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"), {"date": "2026-04-22"})

        self.assertContains(response, "Lunch")
        self.assertNotContains(response, "Taxi")

    def test_expenses_filters_by_month_year_amount_range_and_category(self):
        Expense.objects.create(
            owner=self.user,
            description="Train",
            date=datetime.date(2026, 4, 15),
            amount="45.00",
            category=self.travel,
        )
        Expense.objects.create(
            owner=self.user,
            description="Breakfast",
            date=datetime.date(2026, 4, 16),
            amount="8.00",
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
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
        coffee = Tag.objects.create(owner=self.user, name="Coffee")
        weekday = Tag.objects.create(owner=self.user, name="Weekday")
        weekend = Tag.objects.create(owner=self.user, name="Weekend")

        coffee_expense = Expense.objects.create(
            owner=self.user,
            description="Cafe stop",
            date=datetime.date(2026, 4, 15),
            amount="4.50",
            category=self.food,
        )
        coffee_expense.tags.add(coffee)

        commute_expense = Expense.objects.create(
            owner=self.user,
            description="Morning train",
            date=datetime.date(2026, 4, 15),
            amount="12.00",
            category=self.travel,
        )
        commute_expense.tags.add(weekday)

        brunch_expense = Expense.objects.create(
            owner=self.user,
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
            owner=self.user,
            description="Hotel 2026",
            date=datetime.date(2026, 5, 10),
            amount="120.00",
            category=self.travel,
        )
        Expense.objects.create(
            owner=self.user,
            description="Hotel 2025",
            date=datetime.date(2025, 5, 10),
            amount="110.00",
            category=self.travel,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"), {"month_year": "2026-05"})

        self.assertContains(response, "Hotel 2026")
        self.assertNotContains(response, "Hotel 2025")

    def test_expenses_filters_by_min_amount_only(self):
        Expense.objects.create(
            owner=self.user,
            description="Cheap snack",
            date=datetime.date(2026, 4, 20),
            amount="4.00",
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
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
            owner=self.user,
            description="Expensive",
            date=datetime.date(2026, 4, 20),
            amount="40.00",
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
            description="Cheap",
            date=datetime.date(2026, 4, 20),
            amount="5.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.get(reverse("money_app:expenses"), {"sort": "amount_asc"})
        content = response.content.decode()

        self.assertLess(content.expenses("Cheap"), content.expenses("Expensive"))

    def test_add_expense_requires_login(self):
        response = self.client.get(reverse("money_app:add_expense"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('money_app:add_expense')}",
        )

    def test_logged_in_user_can_delete_their_own_expense(self):
        expense = Expense.objects.create(
            owner=self.user,
            description="Delete me",
            date=datetime.date(2026, 4, 22),
            amount="10.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.post(reverse("money_app:delete_expense", args=[expense.id]))

        self.assertRedirects(response, reverse("money_app:expenses"))
        self.assertFalse(Expense.objects.filter(id=expense.id).exists())

    def test_user_cannot_delete_another_users_expense(self):
        expense = Expense.objects.create(
            owner=self.other_user,
            description="Do not delete",
            date=datetime.date(2026, 4, 22),
            amount="10.00",
            category=self.food,
        )

        self.client.login(username="alice", password="secret123")
        response = self.client.post(reverse("money_app:delete_expense", args=[expense.id]))

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
            owner=self.user,
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
            owner=self.user,
            description="Rent",
            date=datetime.date(2026, 1, 10),
            amount=Decimal("200.00"),
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
            description="Groceries",
            date=datetime.date(2026, 2, 10),
            amount=Decimal("100.00"),
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
            description="Trip",
            date=datetime.date(2025, 6, 10),
            amount=Decimal("700.00"),
            category=self.travel,
        )
        Expense.objects.create(
            owner=self.other_user,
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

    def test_analysis_requires_login(self):
        response = self.client.get(reverse("money_app:analysis"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('money_app:analysis')}",
        )

    def test_analysis_shows_only_logged_in_user_data(self):
        Expense.objects.create(
            owner=self.user,
            description="Lunch",
            date=datetime.date(2026, 4, 22),
            amount="20.00",
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
            description="Taxi",
            date=datetime.date(2026, 4, 23),
            amount="30.00",
            category=self.travel,
        )
        Expense.objects.create(
            owner=self.other_user,
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
            owner=self.user,
            description="Lunch",
            date=datetime.date(current_year, 4, 22),
            amount=Decimal("19.5"),
            category=self.food,
        )
        Expense.objects.create(
            owner=self.user,
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

    def test_analysis_can_be_filtered_by_year(self):
        Expense.objects.create(
            owner=self.user,
            description="Trip 2026",
            date=datetime.date(2026, 5, 10),
            amount="80.00",
            category=self.travel,
        )
        Expense.objects.create(
            owner=self.user,
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
            owner=self.user,
            description="Current year expense",
            date=datetime.date(current_year, 5, 10),
            amount="80.00",
            category=self.travel,
        )
        Expense.objects.create(
            owner=self.user,
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
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))
        expense = Expense.objects.get(description="Groceries")
        self.assertEqual(expense.owner, self.user)
        self.assertEqual(expense.date, datetime.date(2026, 4, 22))

    def test_add_expense_page_shows_tag_input(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:add_expense"))

        self.assertContains(response, "Tags")
        self.assertContains(response, "expense-tag-input")

    def test_logged_in_user_can_create_expense_with_existing_and_new_tags(self):
        Tag.objects.create(owner=self.user, name="Coffee")

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:add_expense"),
            data={
                "description": "Brunch",
                "date": "2026-04-22",
                "amount": "21.50",
                "category": self.food.pk,
                "tags": json.dumps(["coffee", "Weekend"]),
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))

        expense = Expense.objects.get(description="Brunch")
        self.assertCountEqual(
            expense.tags.values_list("name", flat=True),
            ["Coffee", "Weekend"],
        )
        self.assertEqual(Tag.objects.filter(owner=self.user).count(), 2)

    def test_logged_in_user_can_update_expense_tags(self):
        expense = Expense.objects.create(
            owner=self.user,
            description="Lunch",
            date=datetime.date(2026, 4, 22),
            amount="19.50",
            category=self.food,
        )
        expense.tags.add(Tag.objects.create(owner=self.user, name="Weekday"))
        Tag.objects.create(owner=self.user, name="Coffee")

        self.client.login(username="alice", password="secret123")
        response = self.client.post(
            reverse("money_app:edit_expense", args=[expense.id]),
            data={
                "description": "Lunch",
                "date": "2026-04-22",
                "amount": "19.50",
                "category": self.food.pk,
                "tags": json.dumps(["coffee"]),
            },
        )

        self.assertRedirects(response, reverse("money_app:expenses"))

        expense.refresh_from_db()
        self.assertCountEqual(expense.tags.values_list("name", flat=True), ["Coffee"])

    def test_expenses_does_not_show_category_creation_ui(self):
        self.client.login(username="alice", password="secret123")

        response = self.client.get(reverse("money_app:expenses"))

        self.assertNotContains(response, "Add a category")
        self.assertNotContains(response, "Available categories")
        self.assertNotContains(response, "Save category")


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
