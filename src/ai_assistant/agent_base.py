"""
Agent 协议与工具函数（兼容层）。

推荐从 ai_assistant.agent 导入：
  from ai_assistant.agent import AgentRunner, InvokeResult, is_agent_ready, run_agent_warmup
"""
from ai_assistant.agent.protocol import (
    AgentRunner,
    InvokeResult,
    is_agent_ready,
    run_agent_warmup,
)

__all__ = ["AgentRunner", "InvokeResult", "is_agent_ready", "run_agent_warmup"]
