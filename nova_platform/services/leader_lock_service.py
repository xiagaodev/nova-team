"""
Leader调用防重服务

实现Leader调用的防重复触发机制，使用内存状态跟踪。
"""

import json
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session

from nova_platform.models import LeaderInvocationLock
from nova_platform.database import get_session


# 内存中的锁状态缓存（用于快速查找，避免频繁查数据库）
_lock_cache: Dict[str, Dict] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60  # 缓存60秒


def _get_cache_key(project_id: str, invocation_type: str, context_hash: str) -> str:
    """生成缓存键"""
    return f"{project_id}:{invocation_type}:{context_hash}"


def _update_cache(lock: LeaderInvocationLock):
    """更新内存缓存"""
    cache_key = _get_cache_key(
        lock.project_id,
        lock.invocation_type,
        json.loads(lock.invocation_context or "{}").get("hash", "")
    )

    with _cache_lock:
        _lock_cache[cache_key] = {
            "lock_id": lock.id,
            "status": lock.status,
            "locked_at": lock.locked_at,
            "result": lock.result,
            "error": lock.error
        }


def _clear_cache(lock: LeaderInvocationLock):
    """清除内存缓存"""
    cache_key = _get_cache_key(
        lock.project_id,
        lock.invocation_type,
        json.loads(lock.invocation_context or "{}").get("hash", "")
    )

    with _cache_lock:
        _lock_cache.pop(cache_key, None)


def _get_from_cache(project_id: str, invocation_type: str, context_hash: str) -> Optional[Dict]:
    """从内存缓存获取锁状态"""
    cache_key = _get_cache_key(project_id, invocation_type, context_hash)

    with _cache_lock:
        cached = _lock_cache.get(cache_key)
        if cached:
            # 检查是否超时
            if datetime.utcnow() - cached["locked_at"] > timedelta(seconds=_CACHE_TTL):
                _lock_cache.pop(cache_key, None)
                return None
            return cached

    return None


def compute_context_hash(observation: dict, system_hints: dict) -> str:
    """计算决策上下文的哈希值，用于检测重复决策"""
    # 提取关键信息
    key_info = {
        "pending_count": observation.get("status_summary", {}).get("pending", 0),
        "in_progress_count": observation.get("status_summary", {}).get("in_progress", 0),
        "runnable_count": len(observation.get("runnable_tasks", [])),
        "blocker_count": len(observation.get("blockers", [])),
        "idle_agent_count": system_hints.get("idle_agents", 0)
    }

    # 计算哈希
    hash_str = json.dumps(key_info, sort_keys=True)
    return hashlib.md5(hash_str.encode()).hexdigest()[:16]


class LeaderLockService:
    """Leader调用防重服务"""

    @staticmethod
    def acquire_lock(
        session: Session,
        project_id: str,
        invocation_type: str,
        context: dict,
        timeout_seconds: int = 300
    ) -> Optional[LeaderInvocationLock]:
        """
        获取Leader调用锁

        Args:
            session: 数据库会话
            project_id: 项目ID
            invocation_type: 调用类型（decomposition, decision, phase_transition等）
            context: 调用上下文
            timeout_seconds: 超时时间（秒）

        Returns:
            LeaderInvocationLock对象，如果获取失败返回None
        """

        # 计算上下文哈希
        if invocation_type == "decomposition":
            # decomposition锁使用requirement_hash
            context_hash = context.get("requirement_hash", "")
        elif invocation_type == "decision":
            # decision锁使用observation和hints的哈希
            context_hash = compute_context_hash(
                context.get("observation", {}),
                context.get("system_hints", {})
            )
        else:
            # 其他类型使用整个context的哈希
            context_str = json.dumps(context, sort_keys=True)
            context_hash = hashlib.md5(context_str.encode()).hexdigest()[:16]

        # 1. 先检查内存缓存
        cached = _get_from_cache(project_id, invocation_type, context_hash)
        if cached and cached["status"] == "in_progress":
            # 有相同上下文的锁在进行中，返回该锁
            lock_obj = session.query(LeaderInvocationLock).filter_by(id=cached["lock_id"]).first()
            if lock_obj:
                return lock_obj
            return None

        # 2. 检查数据库中是否有相同上下文的锁
        existing = session.query(LeaderInvocationLock).filter(
            LeaderInvocationLock.project_id == project_id,
            LeaderInvocationLock.invocation_type == invocation_type,
            LeaderInvocationLock.status == "in_progress",
            LeaderInvocationLock.locked_at > datetime.utcnow() - timedelta(seconds=timeout_seconds)
        ).all()

        for existing_lock in existing:
            # 检查上下文是否相同
            existing_context = json.loads(existing_lock.invocation_context or "{}")
            if existing_context.get("hash") == context_hash:
                # 完全相同的调用，返回现有锁
                _update_cache(existing_lock)
                return existing_lock

        # 3. 没有相同上下文的锁，创建新锁（允许不同上下文并行）

        # 3. 创建新锁
        lock = LeaderInvocationLock(
            project_id=project_id,
            invocation_type=invocation_type,
            invocation_context=json.dumps({
                "hash": context_hash,
                **context
            }, ensure_ascii=False),
            status="in_progress",
            timeout_seconds=timeout_seconds
        )

        session.add(lock)
        session.commit()
        session.refresh(lock)

        # 更新缓存
        _update_cache(lock)

        return lock

    @staticmethod
    def release_lock(
        session: Session,
        lock: LeaderInvocationLock,
        result: dict = None,
        error: str = None
    ) -> bool:
        """
        释放Leader调用锁

        Args:
            session: 数据库会话
            lock: 锁对象
            result: 执行结果
            error: 错误信息

        Returns:
            是否成功释放
        """

        if lock.status != "in_progress":
            return False

        lock.status = "completed"
        lock.completed_at = datetime.utcnow()

        if result:
            lock.result = json.dumps(result, ensure_ascii=False)

        if error:
            lock.error = error
            lock.status = "failed"

        session.commit()

        # 清除缓存
        _clear_cache(lock)

        return True

    @staticmethod
    def fail_lock(
        session: Session,
        lock: LeaderInvocationLock,
        error: str
    ) -> bool:
        """
        标记锁为失败状态

        Args:
            session: 数据库会话
            lock: 锁对象
            error: 错误信息

        Returns:
            是否成功标记
        """

        if lock.status != "in_progress":
            return False

        lock.status = "failed"
        lock.error = error
        lock.completed_at = datetime.utcnow()

        session.commit()

        # 清除缓存
        _clear_cache(lock)

        return True

    @staticmethod
    def get_lock(session: Session, lock_id: str) -> Optional[LeaderInvocationLock]:
        """获取锁对象"""
        return session.query(LeaderInvocationLock).filter_by(id=lock_id).first()

    @staticmethod
    def get_active_locks(
        session: Session,
        project_id: str,
        invocation_type: str = None
    ) -> list:
        """
        获取活动的锁

        Args:
            session: 数据库会话
            project_id: 项目ID
            invocation_type: 调用类型（可选）

        Returns:
            活动锁列表
        """

        query = session.query(LeaderInvocationLock).filter(
            LeaderInvocationLock.project_id == project_id,
            LeaderInvocationLock.status == "in_progress",
            LeaderInvocationLock.locked_at > datetime.utcnow() - timedelta(minutes=10)
        )

        if invocation_type:
            query = query.filter(LeaderInvocationLock.invocation_type == invocation_type)

        return query.all()

    @staticmethod
    async def wait_for_lock(
        session: Session,
        lock: LeaderInvocationLock,
        timeout: int = 60
    ) -> Optional[dict]:
        """
        等待锁完成

        Args:
            session: 数据库会话
            lock: 锁对象
            timeout: 超时时间（秒）

        Returns:
            锁的结果，如果超时返回None
        """

        import asyncio

        start_time = datetime.utcnow()

        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            # 刷新锁对象
            session.refresh(lock)

            if lock.status == "completed":
                if lock.result:
                    return json.loads(lock.result)
                return {}

            elif lock.status in ["failed", "cancelled"]:
                return {
                    "error": lock.error or "Lock failed or cancelled"
                }

            # 等待一段时间再检查
            await asyncio.sleep(1)

        # 超时
        return None

    @staticmethod
    def cleanup_stale_locks(session: Session) -> int:
        """
        清理过期的锁

        Args:
            session: 数据库会话

        Returns:
            清理的锁数量
        """

        # 找出超时的锁
        stale_locks = session.query(LeaderInvocationLock).filter(
            LeaderInvocationLock.status == "in_progress",
            LeaderInvocationLock.locked_at < datetime.utcnow() - timedelta(minutes=10)
        ).all()

        count = 0
        for lock in stale_locks:
            lock.status = "cancelled"
            lock.error = "Lock timeout"
            lock.completed_at = datetime.utcnow()
            count += 1

        session.commit()

        # 清除缓存
        for lock in stale_locks:
            _clear_cache(lock)

        return count


# 便捷函数
def acquire_decomposition_lock(
    session: Session,
    project_id: str,
    requirement: str
) -> Optional[LeaderInvocationLock]:
    """获取WBS拆解锁"""
    # 计算需求哈希
    req_hash = hashlib.md5(requirement.encode()).hexdigest()[:16]

    return LeaderLockService.acquire_lock(
        session=session,
        project_id=project_id,
        invocation_type="decomposition",
        context={
            "requirement": requirement[:200],  # 只保存前200字符
            "requirement_hash": req_hash
        }
    )


def acquire_decision_lock(
    session: Session,
    project_id: str,
    observation: dict,
    system_hints: dict
) -> Optional[LeaderInvocationLock]:
    """获取决策锁"""
    context_hash = compute_context_hash(observation, system_hints)

    return LeaderLockService.acquire_lock(
        session=session,
        project_id=project_id,
        invocation_type="decision",
        context={
            "observation": observation,
            "system_hints": system_hints
        }
    )


def release_lock(
    session: Session,
    lock: LeaderInvocationLock,
    result: dict = None
) -> bool:
    """释放锁的便捷函数"""
    return LeaderLockService.release_lock(session, lock, result)


def fail_lock(
    session: Session,
    lock: LeaderInvocationLock,
    error: str
) -> bool:
    """标记锁失败的便捷函数"""
    return LeaderLockService.fail_lock(session, lock, error)
