from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_contracts import (
    ExecutionReportWire, KnowledgeSearchRequestWire, PlatformEventWire,
    RunStatus, TaskSubmissionWire,
)


def test_task_submission_wire_is_json_schema_backed_and_round_trips() -> None:
    submission = TaskSubmissionWire.model_validate({
        'owner_id': 'anon:123', 'prompt': 'research',
        'session_id': 'ses-1', 'turn_id': 'turn-1',
        'budget': {'max_tool_calls': 0},
    })
    payload = submission.model_dump(mode='json')
    assert payload['session_id'] == 'ses-1'
    assert payload['budget']['max_tool_calls'] == 0
    assert 'TaskSubmissionWire' in TaskSubmissionWire.model_json_schema()['title']


def test_task_submission_requires_session_and_turn_together() -> None:
    with pytest.raises(ValueError):
        TaskSubmissionWire(owner_id='u1', prompt='research', session_id='ses-1')


def test_wire_models_reject_unknown_fields_and_nonterminal_reports() -> None:
    with pytest.raises(ValueError):
        TaskSubmissionWire(owner_id='u1', prompt='research', unexpected=True)
    with pytest.raises(ValueError):
        ExecutionReportWire(run_id='r1', task_id='t1', status=RunStatus.RUNNING)


def test_platform_event_envelope_contains_durable_replay_identity() -> None:
    event = PlatformEventWire(
        task_id='t1', run_id='r1', seq=3, turn=1, name='delta',
        data={'text': 'answer'}, occurred_at=datetime.now(timezone.utc),
    )
    payload = event.model_dump(mode='json')
    assert (payload['task_id'], payload['run_id'], payload['seq']) == ('t1', 'r1', 3)


def test_knowledge_wire_is_shared_and_uses_product_aliases() -> None:
    request = KnowledgeSearchRequestWire.model_validate({
        'query': 'agent systems', 'topK': 5, 'yearFrom': 2020,
        'venue': ['NeurIPS'],
    })
    payload = request.model_dump(mode='json', by_alias=True)
    assert payload['topK'] == 5
    assert payload['yearFrom'] == 2020
    assert payload['venue'] == ['NeurIPS']
