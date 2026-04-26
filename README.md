# Personal Finance & Investment Tracker (Django)

A privacy-focused personal finance application built with Django.
This project allows users to track expenses, perform custom analysis, and (planned) manage investment portfolios with advanced analytics.

---

## Overview

This project is a **learning-driven application** that explores:

* Backend architecture with Django
* Data modeling for financial systems
* Secure handling of user data
* Analytical features on top of transactional data
* The practical use of modern AI-assisted development workflows

The goal is to balance:

* **Simplicity (for learning and iteration)**
* **Extensibility (for future features like investments & analytics)**
* **Privacy-first design**

---

## AI-Assisted Development

Part of this project was developed with the help of **agentic AI coding tools**, specifically the Codex extension in Visual Studio Code.

The AI was used as a **development assistant**, helping with:

* Generating boilerplate code (views, forms, templates)
* Refactoring and improving existing code, with special focus on HTML templates
* Exploring alternative implementations
* Speeding up iteration during learning

### Important context

* All generated code was **reviewed, adapted, and understood** before being integrated
* The project reflects **human-driven design decisions**, with AI acting as a productivity tool
* The goal was not just to build faster, but to **learn more effectively**

> This approach mirrors modern development workflows, where AI augments—but does not replace—engineering judgment.

---

## Features

### Current

* User authentication (register/login/logout)
* Expense tracking:

  * Amount, category, description, date
* CRUD operations for expenses
* Server-rendered UI using Django templates
* Basic structure for analytics

### Planned

* Investment tracking:

  * Assets (stocks, ETFs, crypto, etc.)
  * Portfolio allocation
* Advanced analytics:

  * Expense breakdowns (category, time)
  * Portfolio distribution (sector, geography)
  * Correlation between assets

---

## Design Principles

### 1. Privacy First

* No third-party analytics
* No unnecessary data collection
* Designed to be self-hostable
* Future: encryption of sensitive fields

### 2. Progressive Complexity

The app evolves in layers:

1. CRUD (expenses)
2. Aggregations (totals, grouping)
3. Analytics (distributions, trends) (planned)
4. Advanced insights (correlation, portfolio analysis) (planned)

---

## 🏗️ Tech Stack

* Backend: Django
* Database: SQLite (default, easily swappable) (MySQL planned)
* Frontend: Django Templates (SSR)

### Future additions

* API layer with Django REST Framework
* Data analysis tools (NumPy / Pandas)

---

## 📁 Project Structure

```id="f3n9m2"
project/
│
├── manage.py
├── .env                # environment variables (ignored)
│
├── mymoney/             # project configuration
│   ├── settings.py
│   └──   urls.py
│
└── money_app/           # main app
    ├── models.py
    ├── views.py
    ├── forms.py
    ├── urls.py
    ├── templates/
    └── migrations/
```

---

## ⚙️ Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd project
```

---

### &#x20;

### 2. Create a virtual environment (pipenv)

 

```
pip install pipenv
pipenv install
pipenv shell
```

 

---

 

### 3. Configure environment variables

 

Create a `.env` file in the root directory:

 

```
DJANGO_SECRET_KEY=your-generated-key
DJANGO_DEBUG=True
```

 

You can generate a secure key with:

 

```
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key(
```

  

---

### 4. Apply migrations

```bash
python manage.py migrate
```

---

### 5. Run the server

```bash
python manage.py runserver
```

---

## Security Notes

* `SECRET_KEY` is loaded from environment variables
* `.env` is ignored via `.gitignore`. Please do not include it on any remote version control system 

---

## Analysis feature

While still on development, the app is intended to provide users with useful analysis metrics and tools that make sense on this domain

---

## Learning Goals

This project explores:

* Django architecture and patterns
* Form handling and validation
* Data modeling for financial domains
* Trade-offs between flexibility and safety (e.g., analytics)
* AI-assisted software development workflows

---

## Future Work

* Investment portfolio module
* API layer for external integrations
* Performance optimizations (caching, indexing)
* Advanced analysis tools for expenses and investments

---

## Contributing

This is primarily a personal/learning project, but ideas and suggestions are welcome.
