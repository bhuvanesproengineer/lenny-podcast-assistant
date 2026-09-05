"""Custom exceptions for the Agent Layer orchestration."""


class AgentError(Exception):
    """Base exception for all agent-related errors."""
    pass


class AgentValidationError(AgentError, ValueError):
    """Raised when user input validation fails (e.g. empty or non-string query)."""
    pass


class AgentExecutionError(AgentError, RuntimeError):
    """Raised when tool execution or agent orchestration fails."""
    pass


class ToolNotFoundError(AgentError, KeyError):
    """Raised when an unrecognized or unregistered tool is invoked."""
    pass
