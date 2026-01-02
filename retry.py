"""Retry utility with exponential backoff for API calls"""

from __future__ import annotations

import time
import functools
from typing import TypeVar, Callable, Any
import logging

logger = logging.getLogger("cubs_scoreboard.retry")

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior"""
    DEFAULT_MAX_RETRIES: int = 3
    DEFAULT_BASE_DELAY: float = 1.0  # seconds
    DEFAULT_MAX_DELAY: float = 60.0  # seconds
    DEFAULT_EXPONENTIAL_BASE: float = 2.0


def retry_with_backoff(
    max_retries: int = RetryConfig.DEFAULT_MAX_RETRIES,
    base_delay: float = RetryConfig.DEFAULT_BASE_DELAY,
    max_delay: float = RetryConfig.DEFAULT_MAX_DELAY,
    exponential_base: float = RetryConfig.DEFAULT_EXPONENTIAL_BASE,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback called on each retry with (exception, attempt_number)

    Returns:
        Decorated function that will retry on failure

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_data():
            return requests.get(url)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    logger.warning(
                        f"{func.__name__} attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )

                    if on_retry:
                        on_retry(e, attempt + 1)

                    time.sleep(delay)

            # This should never be reached, but satisfies type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")

        return wrapper
    return decorator


def retry_api_call(
    func: Callable[..., T],
    *args: Any,
    max_retries: int = RetryConfig.DEFAULT_MAX_RETRIES,
    base_delay: float = RetryConfig.DEFAULT_BASE_DELAY,
    max_delay: float = RetryConfig.DEFAULT_MAX_DELAY,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs: Any
) -> T:
    """
    Execute a function with retry logic and exponential backoff.

    This is a non-decorator version for cases where you can't use decorators.

    Args:
        func: The function to call
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exceptions: Tuple of exception types to catch and retry
        **kwargs: Keyword arguments to pass to func

    Returns:
        The return value of func

    Example:
        result = retry_api_call(statsapi.get, 'game', gamePk=12345)
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(
                    f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(
                base_delay * (RetryConfig.DEFAULT_EXPONENTIAL_BASE ** attempt),
                max_delay
            )

            logger.warning(
                f"{func.__name__} attempt {attempt + 1} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )

            time.sleep(delay)

    # This should never be reached
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop exit")


def retry_http_request(
    url: str,
    method: str = 'GET',
    max_retries: int = RetryConfig.DEFAULT_MAX_RETRIES,
    base_delay: float = RetryConfig.DEFAULT_BASE_DELAY,
    max_delay: float = RetryConfig.DEFAULT_MAX_DELAY,
    timeout: int = 10,
    headers: dict[str, str] | None = None,
    **request_kwargs: Any
) -> Any:
    """
    Execute an HTTP request with retry logic and exponential backoff.

    Args:
        url: The URL to request
        method: HTTP method (GET, POST, etc.)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        timeout: Request timeout in seconds
        headers: Optional HTTP headers
        **request_kwargs: Additional arguments to pass to requests

    Returns:
        The response object

    Example:
        response = retry_http_request('https://api.example.com/data')
        data = response.json()
    """
    import requests
    from requests.exceptions import RequestException

    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = requests.request(
                method,
                url,
                timeout=timeout,
                headers=headers,
                **request_kwargs
            )
            response.raise_for_status()
            return response
        except RequestException as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(
                    f"HTTP {method} {url} failed after {max_retries + 1} attempts: {e}"
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(
                base_delay * (RetryConfig.DEFAULT_EXPONENTIAL_BASE ** attempt),
                max_delay
            )

            logger.warning(
                f"HTTP {method} {url} attempt {attempt + 1} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )

            time.sleep(delay)

    # This should never be reached
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop exit")
