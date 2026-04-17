# Nova Platform

AI collaboration platform for multi-project management with human and AI agents.

## Quick Start

```bash
pip install -e .
nova --help
```

## Commands

### Project
```bash
nova project create <name> --description "..." --template software_dev
nova project list
nova project view <id>
nova project update <id> --status active
nova project delete <id>
```

### Employee
```bash
nova employee add <name> --type human --role developer --skills "python,javascript"
nova employee list
nova employee view <id>
nova employee assign <employee_id> --project <project_id>
```

### TODO
```bash
nova todo add "Task" --project <id> --assign <employee_id> --priority high
nova todo list --project <id>
nova todo list --assign <employee_id>
nova todo update <todo_id> --status completed
nova todo delete <todo_id>
```

### Knowledge
```bash
nova knowledge add --project <id> --title "Title" --content "..." --tags "python"
nova knowledge list --project <id>
nova knowledge search "query"
nova knowledge view <id>
```

### Status
```bash
nova status
nova report --project <id>
```

## Architecture

- **CLI**: Click framework
- **ORM**: SQLAlchemy 2.x
- **Database**: SQLite at `~/.nova-platform/nova.db`
