import click
import os
import sys
import signal
import time
import fcntl
from datetime import datetime
from nova_platform.database import get_session, init_db
from nova_platform.services import project_service, employee_service, todo_service, agent_service, automation_service
from nova_platform.models import Todo
from nova_platform.config import load_config, get_config, get_server_config, get_env, is_production

# PID file location
PID_DIR = os.path.expanduser("~/.nova-platform")
PID_FILE = os.path.join(PID_DIR, "nova-server.pid")
LOG_FILE = os.path.join(PID_DIR, "nova-server.log")

def pid_file_exists():
    """Check if PID file exists and process is running."""
    if not os.path.exists(PID_FILE):
        return False
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        # Check if process exists
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        # Invalid PID or process doesn't exist
        return False

def read_pid():
    """Read PID from file."""
    try:
        with open(PID_FILE, 'r') as f:
            return int(f.read().strip())
    except:
        return None

def remove_pid_file():
    """Remove stale PID file."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

def ensure_pid_dir():
    """Ensure PID directory exists."""
    os.makedirs(PID_DIR, exist_ok=True)


@click.group()
@click.pass_context
def cli(ctx):
    """Nova Platform - AI collaboration platform for multi-project management."""
    init_db()
    ctx.ensure_object(dict)
    ctx.obj["session"] = get_session()


# ============================================================
# Server daemon commands
# ============================================================
@cli.group(name="server")
def server():
    """Server daemon management commands."""
    pass


@server.command(name="start")
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", default=None, type=int, help="Port to bind to")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--force", is_flag=True, help="Force start even if already running")
@click.option("--config", "config_path", default=None, help="Path to config file")
def server_start(host, port, debug, force, config_path):
    """Start the Nova Platform web server as a daemon."""
    # Load configuration
    if config_path:
        cfg = load_config(config_path)
    else:
        cfg = get_config()
    
    server_cfg = cfg.get("server", {})
    
    # Use CLI args or fall back to config
    bind_host = host if host is not None else server_cfg.get("host", "0.0.0.0")
    bind_port = port if port is not None else server_cfg.get("port", 5000)
    use_debug = debug or cfg.get("environment") == "development"
    
    ensure_pid_dir()
    
    if pid_file_exists():
        pid = read_pid()
        if force:
            click.echo(click.style(f"Force starting... (killing old process {pid})", fg="yellow"))
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
            except ProcessLookupError:
                pass
            remove_pid_file()
        else:
            click.echo(click.style(f"Nova server is already running (PID: {pid})", fg="red"))
            click.echo(f"Use 'nova server start --force' to restart.")
            return
    
    click.echo(f"Starting Nova server on {bind_host}:{bind_port}...")
    if use_debug:
        click.echo(click.style(f"Debug mode enabled ({get_env()} environment)", fg="yellow"))
    
    # Fork the process
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process - wait briefly and check if child started successfully
            time.sleep(0.5)
            if pid_file_exists():
                pid = read_pid()
                click.echo(click.style(f"Nova server started (PID: {pid})", fg="green"))
                click.echo(f"Log file: {LOG_FILE}")
                click.echo(f"Web UI: http://{bind_host}:{bind_port}/")
            else:
                click.echo(click.style("Failed to start server. Check log file.", fg="red"))
            sys.exit(0)
    except OSError as e:
        click.echo(click.style(f"Fork failed: {e}", fg="red"), err=True)
        sys.exit(1)
    
    # Child process - become session leader
    os.setsid()
    
    # Redirect standard file descriptors
    with open(LOG_FILE, 'a') as log:
        # Redirect stdin
        fd = os.open(os.devnull, os.O_RDWR)
        os.dup2(fd, 0)
        os.close(fd)
        # Redirect stdout and stderr to log
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
    
    # Write PID file
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    # Start Flask server
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from app import app
    try:
        app.run(host=bind_host, port=bind_port, debug=use_debug, use_reloader=False)
    except Exception as e:
        with open(LOG_FILE, 'a') as log:
            log.write(f"[FATAL] Server error: {e}\n")
        remove_pid_file()
        os._exit(1)


@server.command(name="stop")
@click.option("--timeout", default=10, type=int, help="Seconds to wait before SIGKILL")
def server_stop(timeout):
    """Stop the Nova Platform server daemon."""
    if not pid_file_exists():
        click.echo(click.style("Nova server is not running.", fg="yellow"))
        return
    
    pid = read_pid()
    click.echo(f"Stopping Nova server (PID: {pid})...")
    
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        click.echo(click.style("Process not found. Removing stale PID file.", fg="yellow"))
        remove_pid_file()
        return
    
    # Wait for process to exit
    for i in range(timeout * 10):
        try:
            os.kill(pid, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            break
    else:
        click.echo(click.style(f"Process did not stop gracefully. Sending SIGKILL...", fg="yellow"))
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
        except ProcessLookupError:
            pass
    
    remove_pid_file()
    click.echo(click.style("Nova server stopped.", fg="green"))


@server.command(name="status")
def server_status():
    """Show the status of the Nova Platform server."""
    if pid_file_exists():
        pid = read_pid()
        try:
            os.kill(pid, 0)
            click.echo(click.style(f"🟢 Nova server is running (PID: {pid})", fg="green"))
            click.echo(f"Log file: {LOG_FILE}")
            # Show config being used
            env = get_env()
            srv = get_server_config()
            click.echo(f"Config: {env} environment")
            click.echo(f"Server: {srv.get('host')}:{srv.get('port')}")
        except ProcessLookupError:
            click.echo(click.style("⚠ PID file exists but process is not running.", fg="yellow"))
            click.echo("Run 'nova server stop' to remove stale PID file.")
    else:
        click.echo(click.style("⚠ Nova server is not running.", fg="red"))


@server.command(name="config")
@click.option("--show", is_flag=True, help="Show current configuration")
@click.option("--init", is_flag=True, help="Initialize config file in ~/.nova-platform/")
def server_config(show, init):
    """Manage Nova server configuration."""
    config_dir = os.path.expanduser("~/.nova-platform")
    config_file = os.path.join(config_dir, "config.yaml")
    
    if init:
        os.makedirs(config_dir, exist_ok=True)
        if os.path.exists(config_file):
            click.echo(click.style(f"Config already exists: {config_file}", fg="yellow"))
        else:
            import shutil
            src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.example.yaml")
            if os.path.exists(src):
                shutil.copy(src, config_file)
                click.echo(click.style(f"Created config: {config_file}", fg="green"))
            else:
                click.echo(click.style("config.example.yaml not found", fg="red"))
        return
    
    if show:
        cfg = get_config()
        import json
        click.echo(json.dumps(cfg, indent=2, default=str))
        return
    
    # Default: show help
    click.echo("Config file locations (checked in order):")
    for loc in ["config.yaml", "~/.nova-platform/config.yaml", "/etc/nova-platform/config.yaml"]:
        expanded = os.path.expanduser(loc)
        exists = "✓" if os.path.exists(expanded) else "✗"
        click.echo(f"  {exists} {expanded}")
    click.echo("")
    click.echo("Use 'nova server config --init' to create a config file.")


@server.command(name="restart")
@click.option("--host", default=None, help="Host to bind to")
@click.option("--port", default=None, type=int, help="Port to bind to")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--config", "config_path", default=None, help="Path to config file")
def server_restart(host, port, debug, config_path):
    """Restart the Nova Platform server daemon."""
    if pid_file_exists():
        ctx = click.get_current_context()
        ctx.invoke(server_stop)
        time.sleep(1)
    ctx = click.get_current_context()
    ctx.invoke(server_start, host=host, port=port, debug=debug, config_path=config_path)


@server.command(name="logs")
@click.option("--lines", default=50, type=int, help="Number of lines to show")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (tail -f)")
def server_logs(lines, follow):
    """Show Nova server logs."""
    if not os.path.exists(LOG_FILE):
        click.echo(click.style("No log file found.", fg="yellow"))
        return
    
    with open(LOG_FILE, 'r') as f:
        # Read last N lines
        all_lines = f.readlines()
        tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
    
    for line in tail_lines:
        click.echo(line.rstrip())
    
    if follow:
        click.echo(click.style("--- Following log (Ctrl+C to exit) ---", fg="cyan"))
        try:
            with open(LOG_FILE, 'r') as f:
                # Seek to end
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(0.5)
                    else:
                        click.echo(line.rstrip())
        except KeyboardInterrupt:
            pass


# Project subcommands
@cli.group(name="project")
def project():
    """Project management commands."""
    pass


@project.command(name="create")
@click.pass_obj
@click.argument("name")
@click.option("--description", default="", help="Project description")
@click.option("--template", type=click.Choice(["software_dev", "content_ops", "general"]), default="general", help="Project template")
def project_create(session, name, description, template):
    """Create a new project."""
    session = session["session"]
    proj = project_service.create_project(session, name, description, template)
    click.echo(click.style(f"Created project: ", fg="green") + click.style(proj.name, bold=True))
    click.echo(f"ID: {proj.id}")


@project.command(name="list")
@click.pass_obj
def project_list(session):
    """List all projects."""
    session = session["session"]
    projects = project_service.list_projects(session)
    if not projects:
        click.echo("No projects found.")
        return
    for p in projects:
        status_color = {"planning": "yellow", "active": "green", "completed": "blue", "paused": "red"}.get(p.status, "white")
        click.echo(f"{p.id[:8]}  {click.style(p.status.upper(), fg=status_color):10}  {p.name}")


@project.command(name="view")
@click.pass_obj
@click.argument("project_id")
def project_view(session, project_id):
    """View project details."""
    session = session["session"]
    proj = project_service.get_project(session, project_id)
    if not proj:
        click.echo(click.style(f"Project not found: {project_id}", fg="red"), err=True)
        return
    click.echo(click.style("Project Details", bold=True))
    click.echo(f"ID:          {proj.id}")
    click.echo(f"Name:        {proj.name}")
    click.echo(f"Description: {proj.description}")
    click.echo(f"Template:    {proj.template}")
    click.echo(f"Status:      {proj.status}")
    click.echo(f"Created:     {proj.created_at.strftime('%Y-%m-%d %H:%M')}")
    members = project_service.get_project_members(session, project_id)
    if members:
        click.echo(f"Members:     {', '.join(m.name for m in members)}")


@project.command(name="update")
@click.pass_obj
@click.argument("project_id")
@click.option("--status", type=click.Choice(["planning", "active", "completed", "paused"]), help="Project status")
def project_update(session, project_id, status):
    """Update project details."""
    session = session["session"]
    proj = project_service.update_project(session, project_id, status=status)
    if not proj:
        click.echo(click.style(f"Project not found: {project_id}", fg="red"), err=True)
        return
    click.echo(click.style(f"Updated project: ", fg="green") + proj.name)


@project.command(name="delete")
@click.pass_obj
@click.argument("project_id")
def project_delete(session, project_id):
    """Delete a project."""
    session = session["session"]
    if project_service.delete_project(session, project_id):
        click.echo(click.style(f"Deleted project: {project_id}", fg="green"))
    else:
        click.echo(click.style(f"Project not found: {project_id}", fg="red"), err=True)


# Employee subcommands
@cli.group(name="employee")
def employee():
    """Employee management commands."""
    pass


@employee.command(name="add")
@click.pass_obj
@click.argument("name")
@click.option("--type", "emp_type", type=click.Choice(["human", "agent", "claude-code"]), default="human", help="Employee type")
@click.option("--role", default="general", help="Employee role")
@click.option("--skills", default="", help="Comma-separated skills")
def employee_add(session, name, emp_type, role, skills):
    """Add a new employee."""
    session = session["session"]
    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []
    
    # 如果是 claaude-code 类型，走 recruit 流程
    if emp_type == "claude-code":
        from nova_platform.services import agent_service
        result = agent_service.recruit_agent(session, name, agent_type="claude-code", role=role, skills=skills_list)
        if result["success"]:
            emp = result["employee"]
            click.echo(click.style(f"Added Claude Code agent: ", fg="green") + click.style(emp.name, bold=True))
            click.echo(f"ID: {emp.id}")
        else:
            click.echo(click.style(f"Failed: ", fg="red") + result.get("error", "Unknown error"), err=True)
        return
    
    emp = employee_service.create_employee(session, name, emp_type, role, skills_list)
    click.echo(click.style(f"Added employee: ", fg="green") + click.style(emp.name, bold=True))
    click.echo(f"ID: {emp.id}")


@employee.command(name="list")
@click.pass_obj
def employee_list(session):
    """List all employees."""
    session = session["session"]
    employees = employee_service.list_employees(session)
    if not employees:
        click.echo("No employees found.")
        return
    for e in employees:
        click.echo(f"{e.id[:8]}  {e.type:6}  {e.role:12}  {e.name}")


@employee.command(name="view")
@click.pass_obj
@click.argument("employee_id")
def employee_view(session, employee_id):
    """View employee details."""
    session = session["session"]
    emp = employee_service.get_employee(session, employee_id)
    if not emp:
        click.echo(click.style(f"Employee not found: {employee_id}", fg="red"), err=True)
        return
    click.echo(click.style("Employee Details", bold=True))
    click.echo(f"ID:      {emp.id}")
    click.echo(f"Name:    {emp.name}")
    click.echo(f"Type:    {emp.type}")
    click.echo(f"Role:    {emp.role}")
    click.echo(f"Skills:  {emp.skills}")
    click.echo(f"Created: {emp.created_at.strftime('%Y-%m-%d %H:%M')}")


@employee.command(name="assign")
@click.pass_obj
@click.argument("employee_id")
@click.option("--project", "project_id", required=True, help="Project ID to assign to")
def employee_assign(session, employee_id, project_id):
    """Assign an employee to a project."""
    session = session["session"]
    if project_service.add_project_member(session, project_id, employee_id):
        click.echo(click.style(f"Assigned employee {employee_id[:8]} to project {project_id[:8]}", fg="green"))
    else:
        click.echo(click.style("Project or employee not found", fg="red"), err=True)


# Todo subcommands
@cli.group(name="todo")
def todo():
    """Todo management commands."""
    pass


@todo.command(name="add")
@click.pass_obj
@click.argument("title")
@click.option("--project", "project_id", required=True, help="Project ID")
@click.option("--assign", "assignee_id", help="Employee ID to assign to")
@click.option("--priority", type=click.Choice(["high", "medium", "low"]), default="medium", help="Task priority")
@click.option("--due-date", "due_date", help="Due date (YYYY-MM-DD)")
def todo_add(session, title, project_id, assignee_id, priority, due_date):
    """Add a new todo."""
    session = session["session"]
    due = None
    if due_date:
        try:
            due = datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            click.echo(click.style(f"Invalid date format: {due_date}. Use YYYY-MM-DD.", fg="red"), err=True)
            return
    t = todo_service.create_todo(session, title, project_id, assignee_id=assignee_id, priority=priority, due_date=due)
    click.echo(click.style(f"Created todo: ", fg="green") + click.style(t.title, bold=True))
    click.echo(f"ID: {t.id}")


@todo.command(name="list")
@click.pass_obj
@click.option("--project", "project_id", help="Filter by project ID")
@click.option("--assign", "assignee_id", help="Filter by assignee ID")
def todo_list(session, project_id, assignee_id):
    """List todos."""
    session = session["session"]
    todos = todo_service.list_todos(session, project_id=project_id, assignee_id=assignee_id)
    if not todos:
        click.echo("No todos found.")
        return
    for t in todos:
        priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(t.priority, "white")
        status_color = {"pending": "yellow", "in_progress": "blue", "completed": "green"}.get(t.status, "white")
        due_str = f" | Due: {t.due_date.strftime('%Y-%m-%d')}" if t.due_date else ""
        click.echo(f"{t.id[:8]}  {click.style(t.status.upper(), fg=status_color):12}  {click.style(t.priority.upper(), fg=priority_color):6}  {t.title}{due_str}")


@todo.command(name="update")
@click.pass_obj
@click.argument("todo_id")
@click.option("--status", type=click.Choice(["pending", "in_progress", "completed"]), help="Todo status")
@click.option("--assign", "assignee_id", help="Assign to employee ID")
def todo_update(session, todo_id, status, assignee_id):
    """Update a todo."""
    session = session["session"]
    t = todo_service.update_todo(session, todo_id, status=status, assignee_id=assignee_id)
    if not t:
        click.echo(click.style(f"Todo not found: {todo_id}", fg="red"), err=True)
        return
    click.echo(click.style(f"Updated todo: ", fg="green") + t.title)


@todo.command(name="delete")
@click.pass_obj
@click.argument("todo_id")
def todo_delete(session, todo_id):
    """Delete a todo."""
    session = session["session"]
    if todo_service.delete_todo(session, todo_id):
        click.echo(click.style(f"Deleted todo: {todo_id}", fg="green"))
    else:
        click.echo(click.style(f"Todo not found: {todo_id}", fg="red"), err=True)


# Status command
@cli.command(name="status")
@click.pass_obj
def status(session):
    """Show overview of all projects with todo counts."""
    session = session["session"]
    projects = project_service.list_projects(session)
    if not projects:
        click.echo("No projects found.")
        return
    click.echo(click.style("Project Status Overview", bold=True))
    click.echo("-" * 60)
    for p in projects:
        todos = session.query(Todo).filter_by(project_id=p.id).all()
        pending = sum(1 for t in todos if t.status == "pending")
        in_progress = sum(1 for t in todos if t.status == "in_progress")
        completed = sum(1 for t in todos if t.status == "completed")
        status_color = {"planning": "yellow", "active": "green", "completed": "blue", "paused": "red"}.get(p.status, "white")
        click.echo(f"\n{click.style(p.name, bold=True)} [{click.style(p.status.upper(), fg=status_color)}]")
        click.echo(f"  {pending} pending | {in_progress} in progress | {completed} completed")


# Report command
@cli.command(name="report")
@click.pass_obj
@click.option("--project", "project_id", required=True, help="Project ID for the report")
def report(session, project_id):
    """Show detailed project report."""
    session = session["session"]
    proj = project_service.get_project(session, project_id)
    if not proj:
        click.echo(click.style(f"Project not found: {project_id}", fg="red"), err=True)
        return
    
    click.echo(click.style("=" * 60, fg="cyan"))
    click.echo(click.style(f"Project Report: {proj.name}", bold=True, fg="cyan"))
    click.echo(click.style("=" * 60, fg="cyan"))
    click.echo(f"Status:   {proj.status}")
    click.echo(f"Template: {proj.template}")
    click.echo(f"Created:  {proj.created_at.strftime('%Y-%m-%d %H:%M')}")
    
    # Members
    members = project_service.get_project_members(session, project_id)
    click.echo(click.style("\nMembers:", bold=True))
    if members:
        for m in members:
            click.echo(f"  - {m.name} ({m.type}, {m.role})")
    else:
        click.echo("  No members assigned.")
    
    # Todos by status
    todos = todo_service.list_todos(session, project_id=project_id)
    for status_group in ["pending", "in_progress", "completed"]:
        group_todos = [t for t in todos if t.status == status_group]
        if group_todos:
            status_color = {"pending": "yellow", "in_progress": "blue", "completed": "green"}.get(status_group, "white")
            click.echo(click.style(f"\n{status_group.upper()}:", bold=True, fg=status_color))
            for t in group_todos:
                assignee = "Unassigned"
                if t.assignee_id:
                    emp = employee_service.get_employee(session, t.assignee_id)
                    if emp:
                        assignee = emp.name
                due_str = f" | Due: {t.due_date.strftime('%Y-%m-%d')}" if t.due_date else ""
                priority_mark = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.priority, "⚪️")
                click.echo(f"  {priority_mark} {t.title}{due_str} | Assignee: {assignee}")


@employee.command(name="recruit")
@click.pass_obj
@click.argument("name")
@click.option("--type", "agent_type", type=click.Choice(["openclaw", "hermes", "claude-code"]), default="openclaw", help="Agent type")
@click.option("--role", default="worker", help="Agent role")
@click.option("--skills", default="", help="Comma-separated skills")
@click.option("--model", default=None, help="Model to use for this agent")
def employee_recruit(session, name, agent_type, role, skills):
    """Recruit a new agent (create + register)."""
    session = session["session"]
    skills_list = [s.strip() for s in skills.split(",") if s.strip()] if skills else []

    result = agent_service.recruit_agent(
        session=session,
        name=name,
        agent_type=agent_type,
        role=role,
        skills=skills_list,
        model=model
    )

    if result["success"]:
        emp = result["employee"]
        click.echo(click.style(f"Recruited agent: ", fg="green") + click.style(emp.name, bold=True))
        click.echo(f"ID:       {emp.id}")
        click.echo(f"Type:     {emp.type}")
        click.echo(f"Agent ID: {emp.agent_id}")
    else:
        click.echo(click.style(f"Failed to recruit agent: ", fg="red") + result.get("error", "Unknown error"), err=True)


@employee.command(name="dispatch")
@click.pass_obj
@click.argument("employee_id")
@click.argument("task")
@click.option("--project", "project_id", default=None, help="Associated project ID")
def employee_dispatch(session, employee_id, task, project_id):
    """Dispatch a task to an agent."""
    session = session["session"]

    result = agent_service.dispatch_task(session, employee_id, task, project_id)

    if result["success"]:
        click.echo(click.style(f"Task dispatched successfully", fg="green"))
        if result.get("output"):
            click.echo(f"\nOutput:\n{result['output'][:500]}")
    else:
        click.echo(click.style(f"Failed to dispatch task: ", fg="red") + result.get("error", "Unknown error"), err=True)


# Project run/subcommand
@cli.group(name="run")
def run_group():
    """Project automation commands."""
    pass


@run_group.command(name="decompose")
@click.pass_obj
@click.argument("project_id")
@click.option("--requirements", required=True, help="Requirements text (use \\n for multiple tasks)")
def run_decompose(session, project_id, requirements):
    """Decompose requirements into TODO list."""
    session = session["session"]

    result = automation_service.decompose_requirements(session, project_id, requirements)

    if result["success"]:
        click.echo(click.style(f"Created {len(result['todos'])} todos:", fg="green"))
        for t in result["todos"]:
            priority_color = {"high": "red", "medium": "yellow", "low": "green"}.get(t.priority, "white")
            click.echo(f"  [{t.priority.upper()}] {t.title}")
    else:
        click.echo(click.style(f"Failed: ", fg="red") + result.get("error", "Unknown error"), err=True)


@run_group.command(name="assign")
@click.pass_obj
@click.argument("project_id")
def run_assign(session, project_id):
    """Auto-assign pending tasks to project members."""
    session = session["session"]

    result = automation_service.auto_assign_tasks(session, project_id)

    if result["success"]:
        click.echo(click.style(f"Assigned {result['assigned']} tasks", fg="green"))
    else:
        click.echo(click.style(f"Failed: ", fg="red") + result.get("error", "Unknown error"), err=True)


@run_group.command(name="start")
@click.pass_obj
@click.argument("project_id")
def run_start(session, project_id):
    """Start project workflow (decompose + assign + activate)."""
    session = session["session"]

    result = automation_service.start_project_workflow(session, project_id)

    if result["success"]:
        click.echo(click.style(f"Project workflow started!", fg="green"))
        click.echo(f"Assigned tasks: {result['assigned_tasks']}")
    else:
        click.echo(click.style(f"Failed: ", fg="red") + result.get("error", "Unknown error"), err=True)


@run_group.command(name="status")
@click.pass_obj
@click.argument("project_id")
def run_status(session, project_id):
    """Show project progress report."""
    session = session["session"]

    report = automation_service.get_progress_report(session, project_id)
    click.echo(report)


# Knowledge subcommands (经验共享)
@cli.group(name="knowledge")
def knowledge():
    """Knowledge/experience sharing commands."""
    pass


from nova_platform.services import knowledge_service


@knowledge.command(name="add")
@click.pass_obj
@click.argument("title")
@click.option("--project", "project_id", help="Project ID")
@click.option("--content", default="", help="Knowledge content")
@click.option("--tags", default="", help="Comma-separated tags")
def knowledge_add(session, title, project_id, content, tags):
    """Add a knowledge entry."""
    session = session["session"]
    tags_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    result = knowledge_service.create_knowledge(session, title, project_id, content, tags_list)

    if result["success"]:
        k = result["knowledge"]
        click.echo(click.style(f"Added knowledge: ", fg="green") + click.style(k.title, bold=True))
        click.echo(f"ID: {k.id}")
    else:
        click.echo(click.style(f"Failed: ", fg="red") + result.get("error", "Unknown error"), err=True)


@knowledge.command(name="search")
@click.pass_obj
@click.argument("query")
@click.option("--project", "project_id", help="Filter by project ID")
def knowledge_search(session, query, project_id):
    """Search knowledge base."""
    session = session["session"]

    results = knowledge_service.search_knowledge(session, query, project_id)

    if results:
        click.echo(click.style(f"Found {len(results)} results:", fg="green"))
        for k in results:
            click.echo(f"\n[{k.id[:8]}] {k.title}")
            if k.tags:
                click.echo(f"  Tags: {k.tags}")
            if k.content:
                click.echo(f"  {k.content[:100]}...")
    else:
        click.echo("No results found.")


@knowledge.command(name="list")
@click.pass_obj
@click.option("--project", "project_id", help="Filter by project ID")
def knowledge_list(session, project_id):
    """List knowledge entries."""
    session = session["session"]

    entries = knowledge_service.list_knowledge(session, project_id)

    if entries:
        click.echo(click.style(f"Knowledge entries ({len(entries)}):", fg="cyan"))
        for k in entries:
            click.echo(f"\n[{k.id[:8]}] {k.title}")
            if k.project_id:
                click.echo(f"  Project: {k.project_id[:8]}")
            if k.tags:
                click.echo(f"  Tags: {k.tags}")
    else:
        click.echo("No knowledge entries yet.")


# OKR subcommands (目标与关键结果)
@cli.group(name="okr")
def okr():
    """OKR (Objectives and Key Results) management commands."""
    pass


from nova_platform.services import okr_service


@okr.command(name="create")
@click.pass_obj
@click.argument("project_id")
@click.argument("objective")
@click.option("--target", "target_value", type=float, required=True, help="目标值")
@click.option("--unit", default="", help="单位 (%, 个, 次等)")
@click.option("--due", "due_date", help="截止日期 (YYYY-MM-DD)")
def okr_create(session, project_id, objective, target_value, unit, due_date):
    """创建新的OKR"""
    session = session["session"]

    from datetime import datetime
    due = None
    if due_date:
        try:
            due = datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            click.echo(click.style(f"Invalid date format: {due_date}. Use YYYY-MM-DD.", fg="red"), err=True)
            return

    okr = okr_service.create_okr(
        session,
        project_id=project_id,
        objective=objective,
        target_value=target_value,
        unit=unit,
        due_date=due
    )

    click.echo(click.style(f"Created OKR: ", fg="green") + click.style(okr.objective, bold=True))
    click.echo(f"ID: {okr.id}")
    click.echo(f"Target: {okr.target_value} {okr.unit}")


@okr.command(name="list")
@click.pass_obj
@click.argument("project_id")
def okr_list(session, project_id):
    """列出项目的所有OKR"""
    session = session["session"]

    okrs = okr_service.get_project_okrs(session, project_id)

    if not okrs:
        click.echo("No OKRs found for this project.")
        return

    click.echo(click.style("OKRs for project:", bold=True) + f" {project_id[:8]}")
    click.echo("-" * 60)

    for okr in okrs:
        status_color = {
            "on_track": "green",
            "at_risk": "red",
            "off_track": "yellow",
            "achieved": "blue"
        }.get(okr.status, "white")

        progress = (okr.current_value / okr.target_value * 100) if okr.target_value > 0 else 0

        click.echo(f"\n[{okr.id[:8]}] {okr.objective}")
        click.echo(f"  进度: {okr.current_value}/{okr.target_value} {okr.unit} ({progress:.1f}%)")
        click.echo(f"  状态: {click.style(okr.status.upper(), fg=status_color)}")
        if okr.due_date:
            click.echo(f"  截止: {okr.due_date.strftime('%Y-%m-%d')}")


@okr.command(name="update")
@click.pass_obj
@click.argument("okr_id")
@click.option("--current", "current_value", type=float, required=True, help="当前值")
def okr_update(session, okr_id, current_value):
    """更新OKR进度"""
    session = session["session"]

    okr = okr_service.update_okr_progress(session, okr_id, current_value)

    if not okr:
        click.echo(click.style(f"OKR not found: {okr_id}", fg="red"), err=True)
        return

    progress = (okr.current_value / okr.target_value * 100) if okr.target_value > 0 else 0

    click.echo(click.style(f"Updated OKR: ", fg="green") + okr.objective)
    click.echo(f"进度: {okr.current_value}/{okr.target_value} {okr.unit} ({progress:.1f}%)")
    click.echo(f"状态: {okr.status.upper()}")


@okr.command(name="health")
@click.pass_obj
@click.argument("project_id")
def okr_health(session, project_id):
    """检查OKR健康度"""
    session = session["session"]

    health = okr_service.check_okr_health(session, project_id)

    overall_color = {
        "healthy": "green",
        "off_track": "yellow",
        "at_risk": "red"
    }.get(health["overall"], "white")

    click.echo(click.style("OKR Health Report", bold=True))
    click.echo("-" * 60)
    click.echo(f"整体健康度: {click.style(health['overall'].upper(), fg=overall_color, bold=True)}")
    click.echo()

    for okr_info in health["okrs"]:
        status_color = {
            "on_track": "green",
            "at_risk": "red",
            "off_track": "yellow",
            "achieved": "blue"
        }.get(okr_info["status"], "white")

        click.echo(f"[{okr_info['id'][:8]}] {okr_info['objective']}")
        click.echo(f"  进度: {okr_info['progress']} - {click.style(okr_info['status'].upper(), fg=status_color)}")
        if okr_info["due_date"]:
            click.echo(f"  截止: {okr_info['due_date']}")


@okr.command(name="summary")
@click.pass_obj
@click.argument("project_id")
def okr_summary(session, project_id):
    """显示OKR摘要统计"""
    session = session["session"]

    summary = okr_service.get_okr_summary(session, project_id)

    click.echo(click.style("OKR Summary", bold=True))
    click.echo("-" * 60)
    click.echo(f"总数: {summary['total']}")
    click.echo(f"已达成: {click.style(str(summary['achieved']), fg='green')}")
    click.echo(f"正轨: {click.style(str(summary['on_track']), fg='green')}")
    click.echo(f"风险: {click.style(str(summary['at_risk']), fg='red')}")
    click.echo(f"偏离: {click.style(str(summary['off_track']), fg='yellow')}")
    if summary['total'] > 0:
        click.echo(f"平均进度: {summary['average_progress']*100:.1f}%")


if __name__ == "__main__":
    cli()
