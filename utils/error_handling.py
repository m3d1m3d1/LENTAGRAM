"""
Утилиты для обработки ошибок и retry-логика.

Предоставляет декораторы и функции для:
- Автоматических повторных попыток при временных ошибках
- Логирования исключений
- Классификации ошибок
"""
import asyncio
import functools
import time
from typing import Optional, Callable, Type, Tuple, Any
from utils.logger import get_logger

logger = get_logger(__name__)


class RetryError(Exception):
    """Исключение, выбрасываемое после исчерпания всех попыток."""
    pass


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger_func: Optional[Callable] = None
) -> Callable:
    """
    Декоратор для автоматических повторных попыток выполнения функции.
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками (секунды)
        backoff: Множитель увеличения задержки после каждой попытки
        exceptions: Кортеж исключений, при которых следует делать retry
        logger_func: Функция для логирования (по умолчанию используется logger.warning)
    
    Returns:
        Декорированная функция с retry-логикой
    
    Example:
        @retry(max_attempts=3, delay=1.0, exceptions=(ConnectionError, TimeoutError))
        async def fetch_data():
            return await api.get_data()
    """
    log_func = logger_func or logger.warning
    
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                current_delay = delay
                last_exception = None
                
                for attempt in range(1, max_attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_attempts:
                            log_func(
                                f"Попытка {attempt}/{max_attempts} не удалась: {e}. "
                                f"Следующая попытка через {current_delay:.2f}с"
                            )
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            break
                    except Exception as e:
                        # Исключения не из списка retry пробрасываем сразу
                        raise
                
                error_msg = f"Все {max_attempts} попыток не удались после {func.__name__}"
                logger.error(error_msg, exc_info=last_exception)
                raise RetryError(error_msg) from last_exception
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                current_delay = delay
                last_exception = None
                
                for attempt in range(1, max_attempts + 1):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        if attempt < max_attempts:
                            log_func(
                                f"Попытка {attempt}/{max_attempts} не удалась: {e}. "
                                f"Следующая попытка через {current_delay:.2f}с"
                            )
                            time.sleep(current_delay)
                            current_delay *= backoff
                        else:
                            break
                    except Exception as e:
                        raise
                
                error_msg = f"Все {max_attempts} попыток не удались после {func.__name__}"
                logger.error(error_msg, exc_info=last_exception)
                raise RetryError(error_msg) from last_exception
            
            return sync_wrapper
    
    return decorator


def handle_errors(
    default_return: Any = None,
    swallow_exceptions: Tuple[Type[Exception], ...] = (),
    error_message: str = "Произошла ошибка при выполнении операции"
) -> Callable:
    """
    Декоратор для обработки ошибок с возможностью возврата значения по умолчанию.
    
    Args:
        default_return: Значение, возвращаемое при ошибке
        swallow_exceptions: Исключения, которые нужно проглатывать
        error_message: Сообщение об ошибке для логирования
    
    Returns:
        Декорированная функция с обработкой ошибок
    
    Example:
        @handle_errors(default_return=[], swallow_exceptions=(ValueError,))
        def parse_data(text: str) -> list:
            return json.loads(text)
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> Any:
                try:
                    return await func(*args, **kwargs)
                except swallow_exceptions as e:
                    logger.warning(f"{error_message}: {e}")
                    return default_return
                except Exception as e:
                    logger.error(f"{error_message}: {e}", exc_info=True)
                    return default_return
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> Any:
                try:
                    return func(*args, **kwargs)
                except swallow_exceptions as e:
                    logger.warning(f"{error_message}: {e}")
                    return default_return
                except Exception as e:
                    logger.error(f"{error_message}: {e}", exc_info=True)
                    return default_return
            
            return sync_wrapper
    
    return decorator


class CircuitBreaker:
    """
    Паттерн Circuit Breaker для защиты от каскадных сбоев.
    
    Если функция постоянно падает, circuit "размыкается" и функция
    перестаёт вызываться на некоторое время, возвращая ошибку сразу.
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        
        self.state = self.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Вызывает функцию с учётом состояния circuit breaker."""
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = self.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit Breaker перешёл в состояние HALF_OPEN")
            else:
                raise CircuitBreakerError("Circuit Breaker в состоянии OPEN")
        
        if self.state == self.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls > self.half_open_max_calls:
                logger.warning("Превышено количество попыток в HALF_OPEN")
                raise CircuitBreakerError("Превышено количество попыток в HALF_OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    async def call_async(self, func: Callable, *args, **kwargs) -> Any:
        """Асинхронный вызов функции с учётом состояния circuit breaker."""
        if self.state == self.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = self.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit Breaker перешёл в состояние HALF_OPEN")
            else:
                raise CircuitBreakerError("Circuit Breaker в состоянии OPEN")
        
        if self.state == self.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls > self.half_open_max_calls:
                logger.warning("Превышено количество попыток в HALF_OPEN")
                raise CircuitBreakerError("Превышено количество попыток в HALF_OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self) -> None:
        """Обработка успешного вызова."""
        self.failure_count = 0
        if self.state == self.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = self.CLOSED
                self.success_count = 0
                logger.info("Circuit Breaker перешёл в состояние CLOSED")
    
    def _on_failure(self) -> None:
        """Обработка неудачного вызова."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            logger.warning("Circuit Breaker перешёл в состояние OPEN (сбой в HALF_OPEN)")
        elif self.failure_count >= self.failure_threshold:
            self.state = self.OPEN
            logger.warning(
                f"Circuit Breaker перешёл в состояние OPEN "
                f"({self.failure_count} сбоев)"
            )


class CircuitBreakerError(Exception):
    """Исключение, выбрасываемое когда Circuit Breaker в состоянии OPEN."""
    pass
