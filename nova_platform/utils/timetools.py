"""
时间处理工具模块

统一使用 UTC+8 时区处理所有时间相关操作
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

# UTC+8 时区
TZ_UTC8 = timezone(timedelta(hours=8))


def now() -> datetime:
    """
    获取当前 UTC+8 时间

    Returns:
        带时区信息的 datetime 对象 (UTC+8)
    """
    return datetime.now(TZ_UTC8)


def now_utc() -> datetime:
    """
    获取当前 UTC 时间（无时区信息）

    注意：此函数仅用于与外部系统交互，内部使用 now()

    Returns:
        不带时区信息的 datetime 对象 (UTC)
    """
    return datetime.utcnow()


def to_utc8(dt: Optional[datetime]) -> Optional[datetime]:
    """
    将任意时区的 datetime 转换为 UTC+8

    Args:
        dt: 输入的 datetime 对象

    Returns:
        UTC+8 时区的 datetime 对象
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # 如果没有时区信息，假设是 UTC，转换为 UTC+8
        return dt.replace(tzinfo=timezone.utc).astimezone(TZ_UTC8)
    else:
        # 如果有时区信息，直接转换为 UTC+8
        return dt.astimezone(TZ_UTC8)


def format_datetime(dt: Optional[datetime], fmt: str = "%Y-%m-%d %H:%M") -> Optional[str]:
    """
    格式化 datetime 为字符串（使用 UTC+8）

    Args:
        dt: datetime 对象
        fmt: 格式字符串

    Returns:
        格式化后的字符串
    """
    if dt is None:
        return None

    # 转换为 UTC+8
    dt_utc8 = to_utc8(dt)
    return dt_utc8.strftime(fmt) if dt_utc8 else None


def format_date(dt: Optional[datetime], fmt: str = "%Y-%m-%d") -> Optional[str]:
    """
    格式化日期为字符串（使用 UTC+8）

    Args:
        dt: datetime 对象
        fmt: 格式字符串

    Returns:
        格式化后的日期字符串
    """
    return format_datetime(dt, fmt)


def format_iso(dt: Optional[datetime]) -> Optional[str]:
    """
    格式化为 ISO 8601 字符串（使用 UTC+8）

    Args:
        dt: datetime 对象

    Returns:
        ISO 8601 格式的字符串
    """
    if dt is None:
        return None

    dt_utc8 = to_utc8(dt)
    return dt_utc8.isoformat() if dt_utc8 else None


def from_iso(iso_str: Optional[str]) -> Optional[datetime]:
    """
    从 ISO 8601 字符串解析为 datetime

    Args:
        iso_str: ISO 8601 格式的字符串

    Returns:
        datetime 对象（带 UTC+8 时区）
    """
    if not iso_str:
        return None

    try:
        dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return to_utc8(dt)
    except (ValueError, AttributeError):
        return None


def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """
    序列化 datetime 为 JSON 友好格式（UTC+8）

    Args:
        dt: datetime 对象

    Returns:
        字符串格式的时间
    """
    return format_datetime(dt)


# 数据库默认值（使用 UTC 时间存储，但在读取时转换为 UTC+8 显示）
def db_default_now() -> datetime:
    """
    数据库默认时间值（存储为 UTC）

    Returns:
        不带时区的 UTC datetime（用于数据库存储）
    """
    return datetime.utcnow()


# 便捷函数
def seconds_ago(seconds: int) -> datetime:
    """获取 N 秒前的时间"""
    return now() - timedelta(seconds=seconds)


def minutes_ago(minutes: int) -> datetime:
    """获取 N 分钟前的时间"""
    return now() - timedelta(minutes=minutes)


def hours_ago(hours: int) -> datetime:
    """获取 N 小时前的时间"""
    return now() - timedelta(hours=hours)


def days_ago(days: int) -> datetime:
    """获取 N 天前的时间"""
    return now() - timedelta(days=days)


def seconds_later(seconds: int) -> datetime:
    """获取 N 秒后的时间"""
    return now() + timedelta(seconds=seconds)


def minutes_later(minutes: int) -> datetime:
    """获取 N 分钟后的时间"""
    return now() + timedelta(minutes=minutes)


def hours_later(hours: int) -> datetime:
    """获取 N 小时后的时间"""
    return now() + timedelta(hours=hours)


def days_later(days: int) -> datetime:
    """获取 N 天后的时间"""
    return now() + timedelta(days=days)
