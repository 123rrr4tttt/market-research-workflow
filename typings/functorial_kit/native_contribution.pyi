from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Generic, TYPE_CHECKING, TypeVar
from .contribution_verification import ContributionVerification
from .contributions import Contribution, ContributionCodec, ContributionObject, ContributionSketch
from .core.failure import Failure, FailureFamily
from .core.vocab import Vocabulary

"""Project one authoritative native definition onto the inert contribution protocol."""
if TYPE_CHECKING:
    ...
Definition = TypeVar("Definition")
Context = TypeVar("Context")
Binding = TypeVar("Binding")
@dataclass(frozen=True, slots=True)
class ProjectedContributionSpec:
    """Factory-free projection input derived from one native definition.

    The projection reuses the kit's native declarations. It deliberately has no ``factory``
    field; runtime capabilities remain on :class:`NativeContribution`.
    """
    id: str
    owner: str
    depends_on: tuple[str, ...] = ...
    objects: tuple[ContributionObject, ...] = ...
    codecs: tuple[ContributionCodec, ...] = ...
    vocabularies: tuple[Vocabulary, ...] = ...
    failures: tuple[FailureFamily, ...] = ...
    ports: tuple[Mapping[str, object], ...] = ...
    sketches: tuple[ContributionSketch, ...] = ...


@dataclass(frozen=True, slots=True)
class NativeBindingIssue:
    path: str
    message: str
    ...


@dataclass(frozen=True, slots=True)
class BindingAccepted(Generic[Binding]):
    binding: Binding
    ...


@dataclass(frozen=True, slots=True)
class BindingRejected:
    issues: tuple[NativeBindingIssue, ...]
    ...


@dataclass(frozen=True, slots=True)
class NativeContributionSpec(Generic[Definition, Context, Binding]):
    definition: Definition
    project: Callable[[Definition], ProjectedContributionSpec | Failure]
    assemble: Callable[[Definition, Context], Binding | Failure]
    validate_binding: Callable[[Definition, object], BindingAccepted[Binding] | BindingRejected]
    verification: Callable[[Definition, NativeContribution[Definition, Context, Binding]], ContributionVerification | Failure] | None = ...


@dataclass(frozen=True, slots=True)
class NativeContribution(Generic[Definition, Context, Binding]):
    kind: ClassVar[str] = ...
    definition: Definition
    projection: Contribution[object, object]
    _assembler: Callable[[Definition, Context], Binding | Failure]
    _validator: Callable[[Definition, object], BindingAccepted[Binding] | BindingRejected]
    verification: ContributionVerification | None = ...
    def assemble(self, context: Context) -> Binding | Failure:
        """Explicitly assemble, then validate, the project's native binding."""
        ...



def define_native_contribution(spec: NativeContributionSpec[Definition, Context, Binding]) -> NativeContribution[Definition, Context, Binding] | Failure:
    """Project once; cross-contribution validation remains the composition boundary."""
    ...
