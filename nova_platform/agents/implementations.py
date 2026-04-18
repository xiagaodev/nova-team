"""各智能体实现"""
from nova_platform.agents.base import (
    BaseAgent, AgentType, AgentConfig, AgentResult
)
import subprocess
import os
import time
import shutil


class OpenClawAgent(BaseAgent):
    """OpenClaw 智能体"""

    @property
    def type(self) -> AgentType:
        return AgentType.OPENCLAW

    def is_available(self) -> bool:
        return shutil.which("openclaw") is not None

    def execute(self, prompt: str) -> AgentResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["openclaw", "sessions_spawn", "-t", prompt],
                cwd=self.config.working_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            return AgentResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                duration=time.time() - start
            )
        except subprocess.TimeoutExpired:
            return AgentResult(False, error="Timeout", duration=time.time() - start)
        except Exception as e:
            return AgentResult(False, error=str(e), duration=time.time() - start)


class HermesAgent(BaseAgent):
    """Hermes 智能体"""

    @property
    def type(self) -> AgentType:
        return AgentType.HERMES

    def is_available(self) -> bool:
        return shutil.which("hermes") is not None

    def execute(self, prompt: str) -> AgentResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", prompt],
                cwd=self.config.working_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            return AgentResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                duration=time.time() - start
            )
        except subprocess.TimeoutExpired:
            return AgentResult(False, error="Timeout", duration=time.time() - start)
        except Exception as e:
            return AgentResult(False, error=str(e), duration=time.time() - start)


class ClaudeCodeAgent(BaseAgent):
    """Claude Code 智能体"""

    @property
    def type(self) -> AgentType:
        return AgentType.CLAUDE_CODE

    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    def execute(self, prompt: str) -> AgentResult:
        start = time.time()
        try:
            cmd = ["claude", "--print", "--dangerously-skip-permissions", prompt]
            result = subprocess.run(
                cmd,
                cwd=self.config.working_dir,
                capture_output=True,
                text=True,
                timeout=300,
                input="y\n"  # 自动确认
            )
            return AgentResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                duration=time.time() - start
            )
        except subprocess.TimeoutExpired:
            return AgentResult(False, error="Timeout", duration=time.time() - start)
        except Exception as e:
            return AgentResult(False, error=str(e), duration=time.time() - start)


class CodexAgent(BaseAgent):
    """Codex 智能体"""

    @property
    def type(self) -> AgentType:
        return AgentType.CODEX

    def is_available(self) -> bool:
        return shutil.which("acpx") is not None

    def execute(self, prompt: str) -> AgentResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["acpx", "openclaw", "exec", prompt],
                cwd=self.config.working_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            return AgentResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr if result.returncode != 0 else None,
                duration=time.time() - start
            )
        except subprocess.TimeoutExpired:
            return AgentResult(False, error="Timeout", duration=time.time() - start)
        except Exception as e:
            return AgentResult(False, error=str(e), duration=time.time() - start)


# 后续扩展示例
# class OpenAIChatGPTAgent(BaseAgent):
#     """ChatGPT 智能体"""
#     @property
#     def type(self) -> AgentType:
#         return AgentType.OPENAI
#     
#     def is_available(self) -> bool:
#         return os.environ.get("OPENAI_API_KEY") is not None
#     ...


# 注册表
AGENT_REGISTRY = {
    AgentType.OPENCLAW: OpenClawAgent,
    AgentType.HERMES: HermesAgent,
    AgentType.CLAUDE_CODE: ClaudeCodeAgent,
    AgentType.CODEX: CodexAgent,
}