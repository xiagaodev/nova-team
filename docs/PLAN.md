# Nova Platform — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a CLI-based collaboration platform MVP with Python/Click/SQLAlchemy, supporting multi-project management, employee (human + agent) management, TODO system, and knowledge sharing.

**Architecture:** Single CLI tool `nova` with subcommands for project/employee/todo/knowledge management. SQLite database at `~/.nova-platform/nova.db`. No web UI in MVP.

**Tech Stack:** Python 3.10+, Click 8.x, SQLAlchemy 2.x, SQLite

---

## Task 1: Create project scaffold

**Files to create:**
- `/home/oops/projects/nova-platform/pyproject.toml` (setuptools, click, sqlalchemy dependencies, nova console script entry)
- `/home/oops/projects/nova-platform/nova_platform/__init__.py`
- `/home/oops/projects/nova-platform/nova_platform/services/__init__.py`
- `/home/oops/projects/nova-platform/tests/__init__.py`
- `/home/oops/projects/nova-platform/README.md` (basic usage docs)

**Verify:** `pip install -e /home/oops/projects/nova-platform && nova --help`

---

## Task 2: Create SQLAlchemy models

**Files to create:**
- `/home/oops/projects/nova-platform/nova_platform/models.py` — Contains Base, Project, Employee, ProjectMember, Todo, Knowledge classes

**Verify:** `python -c "from nova_platform.models import Project, Employee, Todo, Knowledge; print('models ok')"`

---

## Task 3: Create database module

**Files to create:**
- `/home/oops/projects/nova-platform/nova_platform/database.py` — init_db(), get_session(), DATA_DIR=~/.nova-platform/

**Verify:** `python -c "from nova_platform.database import init_db, get_session; init_db(); print('db ok')"`

---

## Task 4: Create service layer

**Files to create:**
- `/home/oops/projects/nova-platform/nova_platform/services/__init__.py`
- `/home/oops/projects/nova-platform/nova_platform/services/project_service.py` — create_project, list_projects, get_project, update_project, delete_project, get_project_members, add_project_member, get_employee_projects
- `/home/oops/projects/nova-platform/nova_platform/services/employee_service.py` — create_employee, list_employees, get_employee, update_employee, delete_employee, get_employee_skills
- `/home/oops/projects/nova-platform/nova_platform/services/todo_service.py` — create_todo, list_todos, get_todo, update_todo, delete_todo
- `/home/oops/projects/nova-platform/nova_platform/services/knowledge_service.py` — create_knowledge, list_knowledge, get_knowledge, search_knowledge, update_knowledge, delete_knowledge

**Verify:** `python -c "from nova_platform.services.project_service import create_project; print('services ok')"`

---

## Task 5: Create CLI commands

**Files to create:**
- `/home/oops/projects/nova-platform/nova_platform/cli.py` — Main Click group with subcommands:
  - `project create/list/view/update/delete`
  - `employee add/list/view/assign`
  - `todo add/list/update/delete`
  - `knowledge add/list/view/search/delete`
  - `status` (overview of all projects)
  - `report` (detailed project report)

Each command:
- Uses `@click.pass_obj` to get db session
- Calls appropriate service function
- Prints formatted output using `click.echo` and `click.style`
- Handles errors gracefully

**Verify:**
```bash
nova --help
nova project --help
nova employee --help
nova todo --help
nova knowledge --help
nova status --help
```

---

## Task 6: Write unit tests

**Files to create:**
- `/home/oops/projects/nova-platform/tests/conftest.py` — pytest fixtures (test db session)
- `/home/oops/projects/nova-platform/tests/test_projects.py`
- `/home/oops/projects/nova-platform/tests/test_employees.py`
- `/home/oops/projects/nova-platform/tests/test_todos.py`
- `/home/oops/projects/nova-platform/tests/test_knowledge.py`

**Verify:** `pytest tests/ -v`

---

## Task 7: Final verification

Run all commands end-to-end:
1. `nova project create "Test Project" --template software_dev`
2. `nova employee add "Alice" --type human --role developer --skills "python,go"`
3. `nova todo add "Build login" --project <id> --assign <employee_id> --priority high`
4. `nova knowledge add --project <id> --title "API Design" --content "REST API guidelines" --tags "api,rest"`
5. `nova status`
6. `nova report --project <id>`
7. `nova knowledge search "REST"`

All should execute without errors and produce meaningful output.

---

## Dependencies

- click>=8.0.0
- sqlalchemy>=2.0.0
- pytest>=7.0.0 (dev)
