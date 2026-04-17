from click.testing import CliRunner
from nova_platform.cli import cli
from nova_platform.models import Project
from nova_platform.database import init_db, get_session


def test_status_command():
    """Test the status command."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create a test database
        result = runner.invoke(cli, ['status'])
        # Should complete without error (may show no projects)
        assert result.exit_code == 0 or "No projects found" in result.output


def test_todo_add_command():
    """Test todo add command."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Note: This creates a todo but doesn't validate project exists until we add foreign key checks
        result = runner.invoke(cli, ['todo', 'add', 'Test task', '--project', 'fake-id'])
        # Should complete (validation happens at DB level)
        assert result.exit_code == 0 or "not found" in result.output.lower()


def test_project_commands():
    """Test basic project commands."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['project', 'list'])
        assert result.exit_code == 0


def test_employee_commands():
    """Test basic employee commands."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['employee', 'list'])
        assert result.exit_code == 0
