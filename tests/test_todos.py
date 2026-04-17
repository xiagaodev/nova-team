from nova_platform.services.todo_service import (
    create_todo, list_todos, get_todo, update_todo, delete_todo
)
from nova_platform.models import Project


def test_create_todo(session):
    """Test creating a todo."""
    # Create a project first
    project = Project(name="Test Project", description="Test")
    session.add(project)
    session.commit()

    todo = create_todo(session, "Test Task", project.id, priority="high")
    
    assert todo.title == "Test Task"
    assert todo.project_id == project.id
    assert todo.status == "pending"
    assert todo.priority == "high"


def test_list_todos(session):
    """Test listing todos with filters."""
    project = Project(name="Test Project")
    session.add(project)
    session.commit()

    t1 = create_todo(session, "Task 1", project.id, priority="high")
    t2 = create_todo(session, "Task 2", project.id, priority="low")
    
    all_todos = list_todos(session)
    assert len(all_todos) == 2
    
    high_priority = list_todos(session, status="pending")
    assert len(high_priority) == 2


def test_update_todo(session):
    """Test updating a todo."""
    project = Project(name="Test Project")
    session.add(project)
    session.commit()

    todo = create_todo(session, "Task 1", project.id)
    updated = update_todo(session, todo.id, status="completed")
    
    assert updated.status == "completed"


def test_delete_todo(session):
    """Test deleting a todo."""
    project = Project(name="Test Project")
    session.add(project)
    session.commit()

    todo = create_todo(session, "Task 1", project.id)
    result = delete_todo(session, todo.id)
    
    assert result is True
    assert get_todo(session, todo.id) is None
