"""Legacy runtime import path; new application code uses app.composition."""

from app.services.agent.execution.runtime import *  # noqa: F401,F403
from app.services.agent.execution.runtime import AgentRuntime as _ExecutionAgentRuntime
from app.integrations.llm.agent_stream import OpenAICompatProvider
from app.integrations.llm.resolver import load_registry


class AgentRuntime(_ExecutionAgentRuntime):
    """Compatibility adapter for callers that relied on implicit provider setup."""

    def __init__(self, *args, **kwargs):
        if kwargs.get('provider') is None:
            kwargs['provider'] = OpenAICompatProvider()
        model = kwargs.get('model')
        kwargs['model'] = load_registry().resolve_model(
            model, 'agent', require_configured=False).spec.id
        super().__init__(*args, **kwargs)
