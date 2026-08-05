from dataclasses import dataclass

from config import AI_DAILY_REQUEST_LIMIT, AI_DAILY_TOKEN_LIMIT


@dataclass(frozen=True)
class AILimits:
    daily_requests: int
    daily_tokens: int


class AILimitService:
    """Plan-aware AI limits seam; payments/subscriptions can plug in here later."""

    def get_limits_for_user(self, user_id: int | None = None) -> AILimits:
        # Future: load user's plan and return plan-specific limits.
        return AILimits(
            daily_requests=AI_DAILY_REQUEST_LIMIT,
            daily_tokens=AI_DAILY_TOKEN_LIMIT,
        )


ai_limit_service = AILimitService()
