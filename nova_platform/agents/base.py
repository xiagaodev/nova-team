"""Agent 抽象接口"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum


class AgentType(Enum):
    """支持的智能体类型"""
    OPENCLAW = "openclaw"
    HERMES = "hermes"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    # 后续可扩展
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class AgentConfig:
    """智能体配置"""
    agent_type: AgentType
    name: str
    working_dir: Optional[str] = None
    model: Optional[str] = None
    extra_args: Dict[str, Any] = None


@dataclass
class AgentResult:
    """智能体执行结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    duration: float = 0.0


class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, config: AgentConfig):
        self.config = config

    @property
    @abstractmethod
    def type(self) -> AgentType:
        """返回智能体类型"""
        pass

    @abstractmethod
    def execute(self, prompt: str) -> AgentResult:
        """执行任务"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查是否可用"""
        pass

    def check_health(self) -> bool:
        """健康检查，默认使用 is_available"""
        return self.is_available()