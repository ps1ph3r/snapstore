from dataclasses import dataclass
from typing import Callable, Generic, NoReturn, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")
F = TypeVar("F")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Represents a successful outcome wrapping a value."""
    value: T

    __match_args__ = ("value",)

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def map(self, fn: Callable[[T], U]) -> "Ok[U]":
        return Ok(fn(self.value))

    def map_err(self, fn: Callable[[E], F]) -> "Ok[T]":
        return self

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return fn(self.value)


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """Represents a failure outcome wrapping an error."""
    error: E

    __match_args__ = ("error",)

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> NoReturn:
        raise ValueError(f"Called unwrap on Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, fn: Callable[[T], U]) -> "Err[E]":
        return self

    def map_err(self, fn: Callable[[E], F]) -> "Err[F]":
        return Err(fn(self.error))

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Err[E]":
        return self


Result = Union[Ok[T], Err[E]]


def attempt(fn: Callable[[], T]) -> Result[T, str]:
    """Execute an impure action, converting any exception into Err."""
    try:
        return Ok(fn())
    except Exception as err:
        return Err(str(err))

