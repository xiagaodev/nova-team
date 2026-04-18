"""
Nova Platform - Web Dashboard
美观的可视化看板，无需登录
"""

from flask import Flask, jsonify, render_template, send_from_directory, request
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from nova_platform.database import init_db, get_session
from nova_platform.models import Project, Employee, ProjectMember, Todo
from nova_platform.star_office import (
    star_office_bp, STAR_OFFICE_STATIC,
    load_state, save_state, load_agents_state, save_agents_state
)

app = Flask(__name__, static_folder=None)
app.config['JSON_AS_ASCII'] = False

# 注册 Star Office UI 蓝图
app.register_blueprint(star_office_bp, url_prefix='/office')

# Star Office 静态文件路由
@app.route('/static/<path:filename>')
def serve_star_office_static(filename):
    return send_from_directory(STAR_OFFICE_STATIC, filename)

# 代理 Star Office API 到根路径（前端 JS 调用 /status, /agents 等）
@app.route('/status', methods=['GET'])
def proxy_status():
    from nova_platform.star_office import get_status
    return get_status()

@app.route('/agents', methods=['GET'])
def proxy_agents():
    from nova_platform.star_office import get_agents
    return get_agents()

@app.route('/set_state', methods=['POST'])
def proxy_set_state():
    from nova_platform.star_office import set_state
    return set_state()

@app.route('/yesterday-memo', methods=['GET'])
def proxy_yesterday_memo():
    from nova_platform.star_office import get_yesterday_memo
    return get_yesterday_memo()


def get_stats():
    """获取全局统计数据"""
    session = get_session()
    
    total_projects = session.query(Project).count()
    total_employees = session.query(Employee).count()
    total_todos = session.query(Todo).count()
    
    todos_pending = session.query(Todo).filter_by(status='pending').count()
    todos_in_progress = session.query(Todo).filter_by(status='in_progress').count()
    todos_completed = session.query(Todo).filter_by(status='completed').count()
    
    # AI Agent 数量
    ai_agents = session.query(Employee).filter(Employee.type != 'human').count()
    
    return {
        'total_projects': total_projects,
        'total_employees': total_employees,
        'total_todos': total_todos,
        'todos_pending': todos_pending,
        'todos_in_progress': todos_in_progress,
        'todos_completed': todos_completed,
        'ai_agents': ai_agents
    }


def get_projects():
    """获取所有项目及详情"""
    session = get_session()
    projects = session.query(Project).all()
    
    result = []
    for p in projects:
        # 获取项目成员 - 使用 select_from 明确左侧
        members = session.query(Employee).select_from(ProjectMember).join(
            Employee, Employee.id == ProjectMember.employee_id
        ).filter(ProjectMember.project_id == p.id).all()
        
        # 获取项目任务统计
        todos = session.query(Todo).filter_by(project_id=p.id).all()
        pending = sum(1 for t in todos if t.status == 'pending')
        in_progress = sum(1 for t in todos if t.status == 'in_progress')
        completed = sum(1 for t in todos if t.status == 'completed')
        total = len(todos)
        
        # 计算完成度
        progress = int(completed / total * 100) if total > 0 else 0
        
        # 获取任务列表
        todo_list = [{
            'id': t.id,
            'title': t.title,
            'status': t.status,
            'priority': t.priority,
            'assignee': None,
            'due_date': t.due_date.strftime('%Y-%m-%d %H:%M') if t.due_date else None
        } for t in todos]
        
        # 查找 assignee 名称
        for t in todo_list:
            if t['assignee'] is None and todos[todo_list.index(t)].assignee_id:
                emp = session.query(Employee).get(todos[todo_list.index(t)].assignee_id)
                if emp:
                    t['assignee'] = emp.name
        
        result.append({
            'id': p.id,
            'name': p.name,
            'description': p.description,
            'status': p.status,
            'template': p.template,
            'created_at': p.created_at.strftime('%Y-%m-%d %H:%M'),
            'progress': progress,
            'stats': {
                'total': total,
                'pending': pending,
                'in_progress': in_progress,
                'completed': completed
            },
            'members': [{'id': m.id, 'name': m.name, 'type': m.type, 'role': m.role} for m in members],
            'todos': todo_list
        })
    
    return result


def get_employees():
    """获取所有员工"""
    session = get_session()
    employees = session.query(Employee).all()
    
    result = []
    for e in employees:
        # 获取该员工的任务
        todos = session.query(Todo).filter_by(assignee_id=e.id).all()
        
        result.append({
            'id': e.id,
            'name': e.name,
            'type': e.type,
            'role': e.role,
            'skills': e.skills,
            'created_at': e.created_at.strftime('%Y-%m-%d %H:%M'),
            'todo_count': len(todos),
            'todos': [{
                'id': t.id,
                'title': t.title,
                'status': t.status,
                'priority': t.priority,
                'project_id': t.project_id
            } for t in todos]
        })
    
    return result


@app.route('/')
def index():
    """渲染整合后的主界面"""
    return render_template('index.html')


@app.route('/api/stats')
def api_stats():
    """全局统计"""
    return jsonify(get_stats())


@app.route('/api/projects')
def api_projects():
    """所有项目"""
    return jsonify(get_projects())


@app.route('/api/employees')
def api_employees():
    """所有员工"""
    return jsonify(get_employees())


@app.route('/api/project/<project_id>')
def api_project(project_id):
    """单个项目详情"""
    session = get_session()
    p = session.query(Project).get(project_id)
    if not p:
        return jsonify({'error': 'Project not found'}), 404
    
    projects = get_projects()
    for proj in projects:
        if proj['id'] == project_id:
            return jsonify(proj)
    
    return jsonify({'error': 'Project not found'}), 404


@app.route('/api/sync-star-office', methods=['POST'])
def sync_star_office():
    """将 Nova Platform 员工状态同步到 Star Office"""
    from nova_platform.star_office import (
        load_agents_state, save_agents_state, STATE_TO_AREA_MAP
    )
    import json
    
    session = get_session()
    employees = session.query(Employee).all()
    
    # 获取当前 agent 状态
    agents = load_agents_state()
    
    # 构建员工状态映射
    for emp in employees:
        state = "idle"
        detail = emp.role or "待命中"
        
        # 根据员工类型和任务状态确定状态
        if emp.type == "human":
            state = "idle"
        else:
            # AI Agent，查找当前任务
            active_todo = session.query(Todo).filter(
                Todo.assignee_id == emp.id,
                Todo.status == "in_progress"
            ).first()
            if active_todo:
                state = "executing"
                detail = f"执行: {active_todo.title[:20]}"
            else:
                pending_todo = session.query(Todo).filter(
                    Todo.assignee_id == emp.id,
                    Todo.status == "pending"
                ).first()
                if pending_todo:
                    state = "researching"
                    detail = f"准备: {pending_todo.title[:20]}"
                else:
                    state = "idle"
                    detail = "待命中"
        
        # 更新或创建 agent
        existing = next((a for a in agents if a.get("agentId") == emp.id[:20]), None)
        if existing:
            existing["state"] = state
            existing["detail"] = detail
            existing["area"] = STATE_TO_AREA_MAP.get(state, "breakroom")
            existing["name"] = emp.name
        else:
            agents.append({
                "agentId": emp.id[:20],
                "name": emp.name,
                "isMain": False,
                "state": state,
                "detail": detail,
                "updated_at": datetime.now().isoformat(),
                "area": STATE_TO_AREA_MAP.get(state, "breakroom"),
                "source": "nova-sync",
                "joinKey": None,
                "authStatus": "approved",
                "authExpiresAt": None,
                "lastPushAt": datetime.now().isoformat()
            })
    
    save_agents_state(agents)
    
    return jsonify({
        "success": True,
        "synced_agents": len(agents),
        "employees": len(employees)
    })


if __name__ == '__main__':
    init_db()
    print("🚀 Nova Platform Dashboard 启动!")
    print("📊 访问 http://localhost:5000 查看看板")
    app.run(host='0.0.0.0', port=5000, debug=True)
