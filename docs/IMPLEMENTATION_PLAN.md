# Nova Platform — CLI Implementation Plan

> **Missing Components:** `cli.py`, `todo_service.py`, `knowledge_service.py`
> **Goal:** Implement TODO commands, Knowledge commands, Status/Report commands

---

## Overview of Missing Pieces

| File | Status | Purpose |
|------|--------|---------|
| `nova_platform/cli.py` | **MISSING** | Main CLI entry point with all command groups |
| `nova_platform/services/todo_service.py` | **MISSING** | CRUD operations for Todo model |
| `nova_platform/services/knowledge_service.py` | **MISSING** | CRUD + search for Knowledge model |

---

## Step 1: Create `todo_service.py`

**File:** `/home/oops/projects/nova-platform/nova_platform/services/todo_service.py`

Follow the same pattern as `project_service.py` and `employee_service.py`.

```python
from sqlalchemy.orm import Session
from nova_platform.models import Todo
from datetime import datetime
import json


def create_todo(
    session: Session,
    title: str,
    project_id: str,
    description: str = "",
    assignee_id: str = None,
    priority: str = "medium",
    due_date: datetime = None
) -> Todo:
    todo = Todo(
        title=title,
        description=description,
        project_id=project_id,
        assignee_id=assignee_id,
        priority=priority,
        due_date=due_date,
        status="pending"
    )
    session.add(todo)
    session.commit()
    return todo


def list_todos(
    session: Session,
    project_id: str = None,
    assignee_id: str = None,
    status: str = None
) -> list[Todo]:
    query = session.query(Todo)
    if project_id:
        query = query.filter_by(project_id=project_id)
    if assignee_id:
        query = query.filter_by(assignee_id=assignee_id)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Todo.created_at.desc()).all()


def get_todo(session: Session, todo_id: str) -> Todo | None:
    return session.query(Todo).filter_by(id=todo_id).first()


def update_todo(session: Session, todo_id: str, **kwargs) -> Todo | None:
    todo = get_todo(session, todo_id)
    if not todo:
        return None
    # Handle special fields
    if "due_date" in kwargs and kwargs["due_date"] is not None:
        if isinstance(kwargs["due_date"], str):
            from dateutil.parser import parse
            kwargs["due_date"] = parse(kwargs["due_date"])
    for key, value in kwargs.items():
        if hasattr(todo, key) and value is not None:
            setattr(todo, key, value)
    todo.updated_at = datetime.utcnow()
    session.commit()
    return todo


def delete_todo(session: Session, todo_id: str) -> bool:
    todo = get_todo(session, todo_id)
    if not todo:
        return False
    session.delete(todo)
    session.commit()
    return True
```

**Key patterns:**
- `Session` passed as first argument (dependency injection)
- `**kwargs` for flexible updates
- `datetime.utcnow()` for timestamps
- Return `None` on not found, `bool` on delete

---

## Step 2: Create `knowledge_service.py`

**File:** `/home/oops/projects/nova-platform/nova_platform/services/knowledge_service.py`

```python
from sqlalchemy.orm import Session
from nova_platform.models import Knowledge
from datetime import datetime
import json


def create_knowledge(
    session: Session,
    title: str,
    content: str = "",
    project_id: str = None,
    tags: list = None
) -> Knowledge:
    tags_json = json.dumps(tags or [])
    knowledge = Knowledge(
        title=title,
        content=content,
        project_id=project_id,
        tags=tags_json
    )
    session.add(knowledge)
    session.commit()
    return knowledge


def list_knowledge(
    session: Session,
    project_id: str = None,
    global_only: bool = False
) -> list[Knowledge]:
    query = session.query(Knowledge)
    if global_only:
        query = query.filter(Knowledge.project_id.is_(None))
    elif project_id:
        query = query.filter_by(project_id=project_id)
    return query.order_by(Knowledge.created_at.desc()).all()


def get_knowledge(session: Session, knowledge_id: str) -> Knowledge | None:
    return session.query(Knowledge).filter_by(id=knowledge_id).first()


def search_knowledge(session: Session, query_text: str) -> list[Knowledge]:
    pattern = f"%{query_text}%"
    return session.query(Knowledge).filter(
        (Knowledge.title.like(pattern)) |
        (Knowledge.content.like(pattern)) |
        (Knowledge.tags.like(pattern))
    ).order_by(Knowledge.created_at.desc()).all()


def update_knowledge(session: Session, knowledge_id: str, **kwargs) -> Knowledge | None:
    knowledge = get_knowledge(session, knowledge_id)
    if not knowledge:
        return None
    if "tags" in kwargs and kwargs["tags"] is not None:
        kwargs["tags"] = json.dumps(kwargs["tags"])
    for key, value in kwargs.items():
        if hasattr(knowledge, key) and value is not None:
            setattr(knowledge, key, value)
    knowledge.updated_at = datetime.utcnow()
    session.commit()
    return knowledge


def delete_knowledge(session: Session, knowledge_id: str) -> bool:
    knowledge = get_knowledge(session, knowledge_id)
    if not knowledge:
        return False
    session.delete(knowledge)
    session.commit()
    return True
```

**Key patterns:**
- `project_id` is nullable (None = global knowledge)
- `search_knowledge` does LIKE search across title, content, and tags
- Tags stored as JSON string (same as `skills` in Employee model)

---

## Step 3: Create `cli.py`

**File:** `/home/oops/projects/nova-platform/nova_platform/cli.py`

This is the main entry point with all command groups.

### 3.1 Imports and Context

```python
import click
from nova_platform.database import get_session, init_db
from nova_platform.services import project_service, employee_service, todo_service, knowledge_service
```

### 3.2 Main CLI Group

```python
@click.group()
@click.pass_context
def cli(ctx):
    """Nova Platform - AI Collaboration Platform"""
    init_db()  # Ensure database tables exist
    ctx.ensure_object(dict)
    ctx.obj["session"] = get_session()
```

### 3.3 Project Commands

```python
@cli.group(name="project")
def project_group():
    """Project management commands"""
    pass

@project_group.command(name="create")
@click.argument("name")
@click.option("--description", default="", help="Project description")
@click.option("--template", default="general", type=click.Choice(["software_dev", "content_ops", "general"]))
@click.pass_obj
def project_create(session, name, description, template):
    """Create a new project"""
    project = project_service.create_project(session, name, description, template)
    click.echo(f"Created project {click.style(project.id, fg='cyan')}: {project.name}")

@project_group.command(name="list")
@click.pass_obj
def project_list(session):
    """List all projects"""
    projects = project_service.list_projects(session)
    if not projects:
        click.echo("No projects found.")
        return
    for p in projects:
        click.echo(f"{click.style(p.id[:8], fg='cyan')} | {p.status:12} | {p.name}")

@project_group.command(name="view")
@click.argument("project_id")
@click.pass_obj
def project_view(session, project_id):
    """View project details"""
    project = project_service.get_project(session, project_id)
    if not project:
        click.echo(f"Project {project_id} not found.", err=True)
        return
    click.echo(f"Name:     {project.name}")
    click.echo(f"Status:   {project.status}")
    click.echo(f"Template: {project.template}")
    click.echo(f"Created:  {project.created_at}")

@project_group.command(name="update")
@click.argument("project_id")
@click.option("--status", type=click.Choice(["planning", "active", "completed", "paused"]))
@click.pass_obj
def project_update(session, project_id, status):
    """Update project"""
    project = project_service.update_project(session, project_id, status=status)
    if not project:
        click.echo(f"Project {project_id} not found.", err=True)
        return
    click.echo(f"Updated project {project.name}")

@project_group.command(name="delete")
@click.argument("project_id")
@click.pass_obj
def project_delete(session, project_id):
    """Delete a project"""
    if project_service.delete_project(session, project_id):
        click.echo("Project deleted.")
    else:
        click.echo(f"Project {project_id} not found.", err=True)
```

### 3.4 Employee Commands

```python
@cli.group(name="employee")
def employee_group():
    """Employee management commands"""
    pass

@employee_group.command(name="add")
@click.argument("name")
@click.option("--type", "employee_type", default="human", type=click.Choice(["human", "agent"]))
@click.option("--role", default="general", type=click.Choice(["manager", "developer", "designer", "content_writer", "reviewer", "general"]))
@click.option("--skills", default="", help="Comma-separated skills")
@click.pass_obj
def employee_add(session, name, employee_type, role, skills):
    """Add a new employee"""
    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []
    employee = employee_service.create_employee(session, name, employee_type, role, skills_list)
    click.echo(f"Added employee {click.style(employee.id, fg='cyan')}: {employee.name}")

@employee_group.command(name="list")
@click.pass_obj
def employee_list(session):
    """List all employees"""
    employees = employee_service.list_employees(session)
    if not employees:
        click.echo("No employees found.")
        return
    for e in employees:
        click.echo(f"{click.style(e.id[:8], fg='cyan')} | {e.type:6} | {e.role:12} | {e.name}")

@employee_group.command(name="view")
@click.argument("employee_id")
@click.pass_obj
def employee_view(session, employee_id):
    """View employee details"""
    employee = employee_service.get_employee(session, employee_id)
    if not employee:
        click.echo(f"Employee {employee_id} not found.", err=True)
        return
    import json
    skills = json.loads(employee.skills)
    click.echo(f"Name:   {employee.name}")
    click.echo(f"Type:   {employee.type}")
    click.echo(f"Role:   {employee.role}")
    click.echo(f"Skills: {', '.join(skills) if skills else 'none'}")

@employee_group.command(name="assign")
@click.argument("employee_id")
@click.option("--project", "project_id", required=True, help="Project ID")
@click.pass_obj
def employee_assign(session, employee_id, project_id):
    """Assign employee to project"""
    if project_service.add_project_member(session, project_id, employee_id):
        click.echo("Employee assigned to project.")
    else:
        click.echo("Failed to assign employee (project or employee not found).", err=True)
```

### 3.5 TODO Commands

```python
@cli.group(name="todo")
def todo_group():
    """TODO management commands"""
    pass

@todo_group.command(name="add")
@click.argument("title")
@click.option("--project", "project_id", required=True, help="Project ID")
@click.option("--assign", "assignee_id", help="Assignee employee ID")
@click.option("--priority", type=click.Choice(["low", "medium", "high", "urgent"]), default="medium")
@click.option("--due", "due_date", help="Due date (YYYY-MM-DD)")
@click.option("--description", default="", help="Task description")
@click.pass_obj
def todo_add(session, title, project_id, assignee_id, priority, due_date, description):
    """Add a new TODO"""
    from dateutil.parser import parse
    due = parse(due_date) if due_date else None
    todo = todo_service.create_todo(
        session, title, project_id,
        description=description,
        assignee_id=assignee_id,
        priority=priority,
        due_date=due
    )
    click.echo(f"Created TODO {click.style(todo.id, fg='cyan')}: {todo.title}")

@todo_group.command(name="list")
@click.option("--project", "project_id", help="Filter by project")
@click.option("--assign", "assignee_id", help="Filter by assignee")
@click.option("--status", type=click.Choice(["pending", "in_progress", "completed", "cancelled"]), help="Filter by status")
@click.pass_obj
def todo_list(session, project_id, assignee_id, status):
    """List TODOs"""
    todos = todo_service.list_todos(session, project_id=project_id, assignee_id=assignee_id, status=status)
    if not todos:
        click.echo("No TODOs found.")
        return
    for t in todos:
        priority_color = {"urgent": "red", "high": "yellow", "medium": "cyan", "low": "green"}.get(t.priority, "white")
        click.echo(f"{click.style(t.id[:8], fg='cyan')} [{click.style(t.priority.upper(), fg=priority_color)}] {t.status:12} | {t.title}")

@todo_group.command(name="update")
@click.argument("todo_id")
@click.option("--status", type=click.Choice(["pending", "in_progress", "completed", "cancelled"]))
@click.option("--priority", type=click.Choice(["low", "medium", "high", "urgent"]))
@click.option("--assign", "assignee_id", help="Assignee employee ID")
@click.pass_obj
def todo_update(session, todo_id, status, priority, assignee_id):
    """Update a TODO"""
    updates = {}
    if status is not None:
        updates["status"] = status
    if priority is not None:
        updates["priority"] = priority
    if assignee_id is not None:
        updates["assignee_id"] = assignee_id
    todo = todo_service.update_todo(session, todo_id, **updates)
    if not todo:
        click.echo(f"TODO {todo_id} not found.", err=True)
        return
    click.echo(f"Updated TODO: {todo.title}")

@todo_group.command(name="delete")
@click.argument("todo_id")
@click.pass_obj
def todo_delete(session, todo_id):
    """Delete a TODO"""
    if todo_service.delete_todo(session, todo_id):
        click.echo("TODO deleted.")
    else:
        click.echo(f"TODO {todo_id} not found.", err=True)
```

### 3.6 Knowledge Commands

```python
@cli.group(name="knowledge")
def knowledge_group():
    """Knowledge base commands"""
    pass

@knowledge_group.command(name="add")
@click.option("--project", "project_id", help="Project ID (omit for global)")
@click.option("--title", required=True, help="Knowledge title")
@click.option("--content", default="", help="Knowledge content (Markdown)")
@click.option("--tags", default="", help="Comma-separated tags")
@click.pass_obj
def knowledge_add(session, project_id, title, content, tags):
    """Add knowledge entry"""
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    knowledge = knowledge_service.create_knowledge(
        session, title, content,
        project_id=project_id,
        tags=tags_list
    )
    scope = f"project {project_id[:8]}" if project_id else "global"
    click.echo(f"Added knowledge {click.style(knowledge.id, fg='cyan')} to {scope}: {knowledge.title}")

@knowledge_group.command(name="list")
@click.option("--project", "project_id", help="Filter by project")
@click.option("--global", "global_only", is_flag=True, help="Show global knowledge only")
@click.pass_obj
def knowledge_list(session, project_id, global_only):
    """List knowledge entries"""
    entries = knowledge_service.list_knowledge(session, project_id=project_id, global_only=global_only)
    if not entries:
        click.echo("No knowledge entries found.")
        return
    for k in entries:
        scope = "GLOBAL" if k.project_id is None else k.project_id[:8]
        click.echo(f"{click.style(k.id[:8], fg='cyan')} [{scope}] | {k.title}")

@knowledge_group.command(name="view")
@click.argument("knowledge_id")
@click.pass_obj
def knowledge_view(session, knowledge_id):
    """View knowledge entry"""
    knowledge = knowledge_service.get_knowledge(session, knowledge_id)
    if not knowledge:
        click.echo(f"Knowledge {knowledge_id} not found.", err=True)
        return
    import json
    tags = json.loads(knowledge.tags)
    click.echo(f"Title:   {knowledge.title}")
    click.echo(f"Project: {knowledge.project_id or 'Global'}")
    click.echo(f"Tags:    {', '.join(tags) if tags else 'none'}")
    click.echo(f"\n{knowledge.content}")

@knowledge_group.command(name="search")
@click.argument("query")
@click.pass_obj
def knowledge_search(session, query):
    """Search knowledge entries"""
    results = knowledge_service.search_knowledge(session, query)
    if not results:
        click.echo(f"No results for '{query}'.")
        return
    click.echo(f"Found {len(results)} result(s):")
    for k in results:
        click.echo(f"{click.style(k.id[:8], fg='cyan')} | {k.title}")

@knowledge_group.command(name="delete")
@click.argument("knowledge_id")
@click.pass_obj
def knowledge_delete(session, knowledge_id):
    """Delete knowledge entry"""
    if knowledge_service.delete_knowledge(session, knowledge_id):
        click.echo("Knowledge deleted.")
    else:
        click.echo(f"Knowledge {knowledge_id} not found.", err=True)
```

### 3.7 Status Command

```python
@cli.command(name="status")
@click.pass_obj
def status_cmd(session):
    """Show overview of all projects"""
    projects = project_service.list_projects(session)
    if not projects:
        click.echo("No projects found.")
        return

    click.echo(click.style("Nova Platform Status", bold=True))
    click.echo("=" * 50)

    for p in projects:
        # Count todos for project
        todos = todo_service.list_todos(session, project_id=p.id)
        total = len(todos)
        completed = len([t for t in todos if t.status == "completed"])
        pending = len([t for t in todos if t.status == "pending"])
        in_progress = len([t for t in todos if t.status == "in_progress"])

        members = project_service.get_project_members(session, p.id)

        click.echo(f"\n{click.style(p.name, bold=True)} ({p.status})")
        click.echo(f"  ID:         {p.id}")
        click.echo(f"  Template:   {p.template}")
        click.echo(f"  Members:    {len(members)}")
        click.echo(f"  Todos:      {total} total | {completed} done | {in_progress} active | {pending} pending")

    click.echo("\n" + "=" * 50)
    total_projects = len(projects)
    total_todos = len(todo_service.list_todos(session))
    total_employees = len(employee_service.list_employees(session))
    total_knowledge = len(knowledge_service.list_knowledge(session))
    click.echo(f"Total: {total_projects} projects | {total_employees} employees | {total_todos} todos | {total_knowledge} knowledge entries")
```

### 3.8 Report Command

```python
@cli.command(name="report")
@click.option("--project", "project_id", help="Project ID for detailed report")
@click.option("--all", "report_all", is_flag=True, help="Global report across all projects")
@click.pass_obj
def report_cmd(session, project_id, report_all):
    """Generate project reports"""
    if not project_id and not report_all:
        click.echo("Specify --project <id> or --all", err=True)
        return

    if report_all:
        # Global report
        click.echo(click.style("Nova Platform - Global Report", bold=True))
        click.echo("=" * 60)

        projects = project_service.list_projects(session)
        total_todos = 0
        total_completed = 0
        total_members = 0

        for p in projects:
            todos = todo_service.list_todos(session, project_id=p.id)
            members = project_service.get_project_members(session, p.id)
            completed = len([t for t in todos if t.status == "completed"])
            total_todos += len(todos)
            total_completed += completed
            total_members += len(members)

            completion_pct = (completed / len(todos) * 100) if todos else 0
            click.echo(f"\n{p.name}: {completion_pct:.0f}% complete ({completed}/{len(todos)} todos)")

        click.echo("\n" + "=" * 60)
        overall_pct = (total_completed / total_todos * 100) if total_todos else 0
        click.echo(f"Overall: {overall_pct:.0f}% ({total_completed}/{total_todos} todos)")
        click.echo(f"Projects: {len(projects)} | Employees: {total_members} | Knowledge: {len(knowledge_service.list_knowledge(session))}")
        return

    # Single project report
    project = project_service.get_project(session, project_id)
    if not project:
        click.echo(f"Project {project_id} not found.", err=True)
        return

    click.echo(click.style(f"Project Report: {project.name}", bold=True))
    click.echo("=" * 60)

    # Project info
    click.echo(f"\nStatus:     {project.status}")
    click.echo(f"Template:   {project.template}")
    click.echo(f"Created:    {project.created_at}")
    click.echo(f"Updated:    {project.updated_at}")

    # Members
    members = project_service.get_project_members(session, project_id)
    click.echo(f"\nMembers ({len(members)}):")
    if members:
        for m in members:
            click.echo(f"  - {m.name} ({m.type}, {m.role})")
    else:
        click.echo("  None")

    # Todos
    todos = todo_service.list_todos(session, project_id=project_id)
    by_status = {"pending": [], "in_progress": [], "completed": [], "cancelled": []}
    for t in todos:
        by_status[t.status].append(t)

    click.echo(f"\nTodos ({len(todos)}):")
    for status, items in by_status.items():
        if items:
            click.echo(f"  {status}: {len(items)}")
            for t in items[:3]:  # Show first 3
                click.echo(f"    - {t.title} [{t.priority}]")
            if len(items) > 3:
                click.echo(f"    ... and {len(items) - 3} more")

    # Knowledge
    knowledge_entries = knowledge_service.list_knowledge(session, project_id=project_id)
    click.echo(f"\nKnowledge ({len(knowledge_entries)} entries):")
    if knowledge_entries:
        for k in knowledge_entries[:5]:
            click.echo(f"  - {k.title}")
        if len(knowledge_entries) > 5:
            click.echo(f"  ... and {len(knowledge_entries) - 5} more")

    click.echo("\n" + "=" * 60)
```

### 3.9 CLI Entry Point

```python
if __name__ == "__main__":
    cli()
```

---

## Step 4: Update `services/__init__.py`

**File:** `/home/oops/projects/nova-platform/nova_platform/services/__init__.py`

```python
"""Service layer for nova platform"""

from nova_platform.services import project_service
from nova_platform.services import employee_service
from nova_platform.services import todo_service
from nova_platform.services import knowledge_service
```

---

## Step 5: Add `python-dateutil` Dependency

**File:** `/home/oops/projects/nova-platform/pyproject.toml`

Add to dependencies:
```toml
dependencies = [
    "click>=8.0.0",
    "sqlalchemy>=2.0.0",
    "python-dateutil>=2.8.0",
]
```

---

## Verification Commands

After implementation, verify with:

```bash
pip install -e .
nova --help
nova todo --help
nova knowledge --help
nova status --help
nova report --help

# Test flow
nova project create "Test Project" --template software_dev
nova employee add "Alice" --type human --role developer --skills "python,go"
nova todo add "Build login" --project <project_id> --assign <employee_id> --priority high
nova knowledge add --project <project_id> --title "API Design" --content "REST guidelines" --tags "api,rest"
nova status
nova report --project <project_id>
nova knowledge search "REST"
```

---

## Summary of File Changes

| File | Action | Description |
|------|--------|-------------|
| `nova_platform/services/todo_service.py` | **CREATE** | Todo CRUD service |
| `nova_platform/services/knowledge_service.py` | **CREATE** | Knowledge CRUD + search service |
| `nova_platform/services/__init__.py` | **UPDATE** | Import new services |
| `nova_platform/cli.py` | **CREATE** | All CLI commands |
| `pyproject.toml` | **UPDATE** | Add `python-dateutil` dependency |
