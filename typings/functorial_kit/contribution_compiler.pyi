from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TYPE_CHECKING, TypeVar
from .contribution_verification import ContributionVerification
from .core.failure import Failure
from .native_contribution import BindingAccepted, BindingRejected, NativeContribution, ProjectedContributionSpec

"""Compile a native semantic source through a reusable contribution rule."""
if TYPE_CHECKING:
    ...
Source = TypeVar("Source")
Definition = TypeVar("Definition")
Context = TypeVar("Context")
Binding = TypeVar("Binding")
@dataclass(frozen=True, slots=True)
class NativeContributionRule(Generic[Source, Definition, Context, Binding]):
    """Reusable lowering and native-contribution callbacks for one source family."""
    lower: Callable[[Source], Definition | Failure]
    project: Callable[[Definition], ProjectedContributionSpec | Failure]
    assemble: Callable[[Definition, Context], Binding | Failure]
    validate_binding: Callable[[Definition, object], BindingAccepted[Binding] | BindingRejected]
    verification: Callable[[Definition, NativeContribution[Definition, Context, Binding]], ContributionVerification | Failure] | None = ...


def compile_native_contribution(source: Source, rule: NativeContributionRule[Source, Definition, Context, Binding]) -> NativeContribution[Definition, Context, Binding] | Failure:
    """Lower once, then delegate projection and explicit runtime callbacks to the native API."""
    ...
