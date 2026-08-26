"""Domain failures that callers must handle explicitly."""


class DomainError(RuntimeError):
    """Base class for deterministic domain failures."""


class InvalidTransition(DomainError):
    """Raised when an event cannot advance a case from its current status."""


class VersionConflict(DomainError):
    """Raised when a command was decided against an older case projection."""


class InvalidEventPayload(DomainError):
    """Raised when an event carries missing, conflicting, or unsafe facts."""
