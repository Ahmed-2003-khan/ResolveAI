from fastapi import HTTPException, status


class ResolveAIError(Exception):
    """Base exception for all application errors."""


class NotFoundError(ResolveAIError):
    pass


class ValidationError(ResolveAIError):
    pass


class AllProvidersDownError(ResolveAIError):
    """Raised when every LLM provider has failed or tripped its circuit breaker."""


class WebhookVerificationError(ResolveAIError):
    """Raised when an inbound webhook signature is invalid."""


class PIIRedactionError(ResolveAIError):
    pass


def http_not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def http_bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def http_unauthorized(detail: str = "Unauthorized") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)
