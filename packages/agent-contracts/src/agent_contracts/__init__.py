"""Stable, infrastructure-free contracts between Backend and Agent Platform."""

from .budgets import BudgetLimits, UsageReport
from .events import PlatformEvent
from .knowledge import (
    KnowledgeGraphEdgeWire, KnowledgeGraphNodeWire, KnowledgeGraphQueryWire,
    KnowledgePaperDetailWire, KnowledgePaperGraphWire, KnowledgePaperResultWire,
    KnowledgeProvenanceWire, KnowledgeSearchRequestWire, KnowledgeSearchResponseWire,
)
from .runs import ExecutionReport, RunRecord, RunRequest, RunStatus
from .tasks import TaskRecord, TaskStatus, TaskSubmission
from .wire import (
    AgentConfigWire, BudgetLimitsWire, EventIngestWire, ExecutionReportWire,
    OwnerQueryWire, PlatformEventWire, ReportIngestWire, RunEventsQueryWire,
    RunRecordWire, RunSteerRequestWire, RunSteerResponseWire,
    SessionFileReadRequestWire, SessionFileReadResponseWire, TaskRecordWire,
    TaskSubmissionWire, UsageReportWire, WorkspaceClaimCommitResponseWire,
    WorkspaceClaimPrepareResponseWire, WorkspaceClaimRequestWire,
    WorkspaceCreateRequestWire, WorkspaceCreateResponseWire,
    WorkspaceFileWriteRequestWire, WorkspaceFileWriteResponseWire, validate_history,
)

__all__ = [
    'BudgetLimits', 'ExecutionReport', 'PlatformEvent', 'RunRequest',
    'RunRecord', 'RunStatus', 'TaskRecord', 'TaskStatus', 'TaskSubmission', 'UsageReport',
    'BudgetLimitsWire', 'ExecutionReportWire', 'PlatformEventWire', 'RunRecordWire',
    'TaskRecordWire', 'TaskSubmissionWire', 'UsageReportWire', 'EventIngestWire',
    'ReportIngestWire',
    'KnowledgeGraphEdgeWire', 'KnowledgeGraphNodeWire', 'KnowledgeGraphQueryWire',
    'KnowledgePaperDetailWire',
    'KnowledgePaperGraphWire', 'KnowledgePaperResultWire', 'KnowledgeProvenanceWire',
    'KnowledgeSearchRequestWire', 'KnowledgeSearchResponseWire',
    'AgentConfigWire', 'RunSteerRequestWire', 'RunSteerResponseWire',
    'OwnerQueryWire', 'RunEventsQueryWire', 'SessionFileReadRequestWire',
    'SessionFileReadResponseWire', 'WorkspaceClaimCommitResponseWire',
    'WorkspaceClaimPrepareResponseWire', 'WorkspaceClaimRequestWire',
    'WorkspaceCreateRequestWire', 'WorkspaceCreateResponseWire',
    'WorkspaceFileWriteRequestWire', 'WorkspaceFileWriteResponseWire',
    'validate_history',
]
