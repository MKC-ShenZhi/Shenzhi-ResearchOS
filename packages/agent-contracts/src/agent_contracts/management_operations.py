"""Additive management operations. Existing execution contracts retain ownership."""
from typing import Literal
from uuid import UUID
from pydantic import Field
from .management_phase2 import Identifier, Strict, Target
from .management_config import Note


class TargetReference(Strict):
    kind: Target
    target_id: Identifier


class CheckSummaryRequest(Strict):
    targets: list[TargetReference] = Field(min_length=1, max_length=100)


class ModelReferences(Strict):
    model_ids: list[Identifier] = Field(max_length=120)


class ManagementAction(Strict):
    operation_id: UUID
    kind: Literal['task', 'run', 'worker', 'alert']
    target_id: Identifier
    action: Literal['cancel', 'drain', 'resume', 'acknowledge', 'close']
    reason: Note
    timeout_seconds: int = Field(default=300, ge=10, le=86400)


class ActorManagementAction(ManagementAction):
    actor: Identifier
