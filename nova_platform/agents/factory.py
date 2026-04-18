"""智能体工厂"""
from nova_platform.agents.base import (
    BaseAgent, AgentType, AgentConfig, AgentResult
)
from nova_platform.agents.implementations import AGENT_REGISTRY


class AgentFactory:
    """智能体工厂"""

    @staticmethod
    def create(config: AgentConfig) -> BaseAgent:
        """创建智能体实例"""
        agent_class = AGENT_REGISTRY.get(config.agent_type)
        if agent_class is None:
            raise ValueError(f"不支持的智能体类型: {config.agent_type}")
        return agent_class(config)

    @staticmethod
    def register(agent_type: AgentType, agent_class: type):
        """注册新的智能体类型"""
        AGENT_REGISTRY[agent_type] = agent_class

    @staticmethod
    def available_agents() -> list[AgentType]:
        """返回可用的智能体列表"""
        available = []
        for agent_type, agent_class in AGENT_REGISTRY.items():
            try:
                config = AgentConfig(agent_type=agent_type, name="")
                agent = agent_class(config)
                if agent.is_available():
                    available.append(agent_type)
            except Exception:
                pass
        return available

    @staticmethod
    def create_by_type(agent_type: AgentType, name: str, **kwargs) -> BaseAgent:
        """根据类型创建智能体"""
        config = AgentConfig(agent_type=agent_type, name=name, **kwargs)
        return AgentFactory.create(config)


__all__ = ["AgentFactory", "AgentConfig", "AgentResult"]