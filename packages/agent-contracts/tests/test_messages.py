"""Only the first-stage message contract is accepted at service boundaries."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent_contracts import AIMessage, ExecutionReportWire, PlatformEventWire, validate_history
from agent_contracts.messages import MarkdownBlock, Reference


def message(**overrides):
    return AIMessage(id='m1', created_at=1.0, **overrides)


def test_message_round_trip_and_markdown_discriminator():
    original = message(status='done', blocks=[MarkdownBlock(id='b1', content='结果 [[cite:r1]]')],
                       references=[Reference(id='r1', type='paper', title='A paper', year=2026)])
    assert AIMessage.model_validate_json(original.model_dump_json()) == original
    schema = AIMessage.model_json_schema()
    assert schema['properties']['blocks']['items']['discriminator']['mapping'] == {
        'markdown': '#/$defs/MarkdownBlock',
    }


@pytest.mark.parametrize('block_type', ['image', 'chart', 'graph', 'knowledge_entity', 'file', 'custom'])
def test_unimplemented_blocks_are_not_part_of_v1(block_type):
    with pytest.raises(ValidationError):
        message(blocks=[{'id': 'b1', 'type': block_type}])


@pytest.mark.parametrize('overrides', [
    {'status': 'invented'}, {'schema_version': 2}, {'created_at': float('nan')},
    {'metadata': []}, {'unexpected': 'value'},
    {'blocks': [MarkdownBlock(id='b1'), MarkdownBlock(id='b1')]},
    {'blocks': [MarkdownBlock(id='b1', content='[[cite:missing]]')]},
    {'blocks': [MarkdownBlock(id='b1', content='[[cite:]]')]},
    {'references': [Reference(id='r1', type='webpage', title='a'),
                    Reference(id='r1', type='webpage', title='b')]},
])
def test_invalid_message_rejected(overrides):
    payload = {'id': 'm1', 'created_at': 1.0, **overrides}
    with pytest.raises(ValidationError):
        AIMessage.model_validate(payload)


def test_structured_events_and_reports_validated_without_rejecting_legacy_data():
    envelope = dict(task_id='t1', run_id='r1', seq=1, turn=1, occurred_at=datetime.now(timezone.utc))
    PlatformEventWire(**envelope, name='delta', data={'text': 'old event'})
    PlatformEventWire(**envelope, name='message_end', data={'message': message(status='done').model_dump()})
    with pytest.raises(ValidationError):
        PlatformEventWire(**envelope, name='message_end', data={'message': message().model_dump()})
    with pytest.raises(ValidationError):
        PlatformEventWire(**envelope, name='block_delta', data={'delta': 'missing identity'})
    ExecutionReportWire(task_id='t1', run_id='r1', status='completed', result={'final_text': 'old'})
    with pytest.raises(ValidationError):
        ExecutionReportWire(task_id='t1', run_id='r1', status='completed', result={'message': {}})
    validate_history([{'kind': 'tool', 'call_id': 'c1', 'name': 'echo', 'content': 'old'}])
    with pytest.raises(ValidationError):
        validate_history([{'kind': 'tool', 'call_id': 'c1', 'name': 'echo', 'content': 'new',
                           'references': [{'title': 'invalid'}]}])
