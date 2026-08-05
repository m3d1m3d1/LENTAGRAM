import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from config import AI_FAILURE_COOLDOWN_SECONDS
from services.ai.limits import ai_limit_service
from services.database import get_connection

logger = logging.getLogger(__name__)

REASONS = {"quota_exceeded", "provider_error", "timeout", "unknown"}


@dataclass
class AIAvailabilityState:
    is_available: bool
    disabled_reason: str | None
    disabled_at: str | None
    last_check_time: str | None


class AIUnavailableError(RuntimeError):
    def __init__(self, reason: str = "unknown"):
        self.reason = reason if reason in REASONS else "unknown"
        super().__init__(self.reason)


class AIAvailabilityManager:
    def _now(self) -> str:
        return datetime.utcnow().isoformat(timespec="seconds")

    def get_state(self) -> AIAvailabilityState:
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ai_availability WHERE id = 1").fetchone()
            if not row:
                conn.execute("INSERT INTO ai_availability (id, is_available, last_check_time) VALUES (1, 1, ?)", (self._now(),))
                conn.commit()
                return AIAvailabilityState(True, None, None, self._now())
            return AIAvailabilityState(bool(row["is_available"]), row["disabled_reason"], row["disabled_at"], row["last_check_time"])

    def can_attempt_after_cooldown(self) -> bool:
        state = self.get_state()
        if state.is_available or not state.disabled_at:
            return state.is_available
        try:
            disabled_at = datetime.fromisoformat(state.disabled_at)
        except ValueError:
            return False
        return datetime.utcnow() - disabled_at >= timedelta(seconds=AI_FAILURE_COOLDOWN_SECONDS)

    def mark_available(self) -> None:
        with get_connection() as conn:
            conn.execute("""
                UPDATE ai_availability
                SET is_available = 1, disabled_reason = NULL, disabled_at = NULL,
                    last_check_time = ?, notification_sent_at = NULL
                WHERE id = 1
            """, (self._now(),))
            conn.commit()

    def mark_unavailable(self, reason: str) -> bool:
        reason = reason if reason in REASONS else "unknown"
        now = self._now()
        with get_connection() as conn:
            row = conn.execute("SELECT is_available FROM ai_availability WHERE id = 1").fetchone()
            was_available = (row is None) or bool(row["is_available"])
            conn.execute("""
                INSERT INTO ai_availability (id, is_available, disabled_reason, disabled_at, last_check_time)
                VALUES (1, 0, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    is_available = 0,
                    disabled_reason = excluded.disabled_reason,
                    disabled_at = excluded.disabled_at,
                    last_check_time = excluded.last_check_time
            """, (reason, now, now))
            conn.commit()
        logger.warning("AI disabled: %s", reason)
        return was_available

    def ensure_can_call(self, estimated_input_tokens: int = 0) -> None:
        state = self.get_state()
        if not state.is_available and not self.can_attempt_after_cooldown():
            raise AIUnavailableError(state.disabled_reason or "unknown")

        stats = self.get_today_stats()
        limits = ai_limit_service.get_limits_for_user()
        if limits.daily_requests > 0 and stats["total_requests"] >= limits.daily_requests:
            self.mark_unavailable("quota_exceeded")
            raise AIUnavailableError("quota_exceeded")
        used_tokens = stats["input_tokens"] + stats["output_tokens"]
        if limits.daily_tokens > 0 and used_tokens + estimated_input_tokens >= limits.daily_tokens:
            self.mark_unavailable("quota_exceeded")
            raise AIUnavailableError("quota_exceeded")

    def record_usage(self, *, success: bool, input_tokens: int = 0, output_tokens: int = 0, provider_error: bool = False, rejected: bool = False) -> None:
        today = date.today().isoformat()
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO ai_usage_stats (date, total_requests, successful_requests, failed_requests, rejected_posts, provider_errors, input_tokens, output_tokens, updated_at)
                VALUES (?, 1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date) DO UPDATE SET
                    total_requests = total_requests + 1,
                    successful_requests = successful_requests + excluded.successful_requests,
                    failed_requests = failed_requests + excluded.failed_requests,
                    rejected_posts = rejected_posts + excluded.rejected_posts,
                    provider_errors = provider_errors + excluded.provider_errors,
                    input_tokens = input_tokens + excluded.input_tokens,
                    output_tokens = output_tokens + excluded.output_tokens,
                    updated_at = CURRENT_TIMESTAMP
            """, (today, 1 if success else 0, 0 if success else 1, 1 if rejected else 0, 1 if provider_error else 0, input_tokens, output_tokens))
            conn.commit()

    def record_rejected_post(self) -> None:
        today = date.today().isoformat()
        with get_connection() as conn:
            conn.execute("""
                INSERT INTO ai_usage_stats (date, rejected_posts, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(date) DO UPDATE SET
                    rejected_posts = rejected_posts + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, (today,))
            conn.commit()

    def get_today_stats(self) -> dict:
        today = date.today().isoformat()
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM ai_usage_stats WHERE date = ?", (today,)).fetchone()
            if not row:
                return {"total_requests": 0, "successful_requests": 0, "failed_requests": 0, "rejected_posts": 0, "provider_errors": 0, "input_tokens": 0, "output_tokens": 0}
            return dict(row)

    def reset_daily(self) -> None:
        with get_connection() as conn:
            conn.execute("DELETE FROM ai_usage_stats WHERE date = ?", (date.today().isoformat(),))
            conn.commit()
        self.mark_available()

    def get_status_text(self, plan_limits: dict | None = None) -> str:
        limits = plan_limits or ai_limit_service.get_limits_for_user().__dict__
        state = self.get_state(); stats = self.get_today_stats()
        return (
            "AI STATUS\n\n"
            f"Available:\n{state.is_available}\n\n"
            f"Reason:\n{state.disabled_reason or '-'}\n\n"
            f"Requests:\n{stats['total_requests']} / {limits['daily_requests']}\n\n"
            f"Successful:\n{stats['successful_requests']}\n\n"
            f"Failed:\n{stats['failed_requests']}\n\n"
            "Tokens:\n"
            f"Input:\n{stats['input_tokens']}\n\n"
            f"Output:\n{stats['output_tokens']}"
        )


ai_availability_manager = AIAvailabilityManager()
