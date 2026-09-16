"""Direct Chat-service regression tests for bounded Knowledge degradation."""

import asyncio
import unittest
from unittest.mock import patch

from app.schemas.chat import CreateSessionBody
from app.schemas.knowledge import KnowledgeError, KnowledgeSearchResponse, PaperSearchResult, Provenance
from app.services import chat
from app.services.knowledge import KnowledgeServiceError
from app.services.sessions import repository


OWNER_KEY = "anon:00000000-0000-4000-8000-000000000101"


def paper(paper_id: str, abstract: str | None = "abstract") -> PaperSearchResult:
    return PaperSearchResult(
        id=paper_id,
        title=f"Paper {paper_id}",
        abstract=abstract,
        authors=["Author"],
        year=2024,
        venue="Venue",
        score=0.9,
        rank=1,
        provenance=Provenance(external_id=paper_id),
    )


class KnowledgeStub:
    def __init__(self, response=None, error=None):
        self.response = response or KnowledgeSearchResponse(results=[])
        self.error = error
        self.calls = []

    async def search(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.response


class SequenceProvider:
    answers: list[str] = []
    calls: list[list[dict]] = []

    async def stream(self, messages, model, mode):
        self.calls.append(messages)
        yield {"text": self.answers.pop(0) if self.answers else "普通回答。"}

    async def followups(self, question, answer):
        return []


class Knowledge2ChatDegradationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from app.core.database import dispose_engine
        await dispose_engine()
        await repository.clear()
        SequenceProvider.answers = ["普通回答。"]
        SequenceProvider.calls = []
        self.provider_patch = patch.object(chat, "ModelProvider", SequenceProvider)
        self.provider_patch.start()
        self.knowledge = KnowledgeStub(KnowledgeSearchResponse(results=[paper("paper-a")]))
        self.knowledge_patch = patch.object(chat, "knowledge_service", self.knowledge)
        self.knowledge_patch.start()

    async def asyncTearDown(self):
        await repository.close()
        self.knowledge_patch.stop()
        self.provider_patch.stop()

    async def generate(self, *, enabled=True):
        body = CreateSessionBody.model_validate({
            "question": "用一句话解释 Transformer。",
            "capabilities": {"knowledge": {"enabled": enabled}},
        })
        message = await chat.prepare_message(body, OWNER_KEY)
        await chat.generate(message)
        return message

    async def test_zero_result_falls_back_once_without_reference_data(self):
        self.knowledge.response = KnowledgeSearchResponse(results=[])
        message = await self.generate()

        self.assertEqual(message.status, "done", repr(message.events))
        self.assertEqual(len(SequenceProvider.calls), 1)
        self.assertNotIn("<reference_data>", SequenceProvider.calls[0][-1]["content"])
        self.assertEqual(message.settings["knowledge_grounding"], "unavailable")
        self.assertIn(chat.NO_KNOWLEDGE_WARNING, message.warnings)

    async def test_no_usable_abstract_falls_back_once(self):
        self.knowledge.response = KnowledgeSearchResponse(results=[paper("paper-a", None)])
        message = await self.generate()

        self.assertEqual(message.status, "done")
        self.assertEqual(len(SequenceProvider.calls), 1)
        self.assertEqual(message.settings["knowledge_grounding"], "unavailable")
        self.assertIn(chat.NO_KNOWLEDGE_WARNING, message.warnings)

    async def test_timeout_and_upstream_unavailable_are_ordinary_fallbacks(self):
        for code, status in (("TIMEOUT", 504), ("UPSTREAM_UNAVAILABLE", 503)):
            with self.subTest(code=code):
                await repository.clear()
                SequenceProvider.calls = []
                self.knowledge.error = KnowledgeServiceError(
                    KnowledgeError(code=code, message="upstream detail", retryable=True, request_id=None),
                    status_code=status,
                )
                message = await self.generate()

                self.assertEqual(message.status, "done")
                self.assertEqual(len(SequenceProvider.calls), 1)
                self.assertEqual(message.settings["knowledge_grounding"], "unavailable")
                self.assertIn(chat.KNOWLEDGE_SERVICE_WARNING, message.warnings)

    async def test_candidate_without_valid_citation_is_buffered_then_uses_one_plain_fallback(self):
        candidate = "首轮候选 [99]，不能发送。"
        fallback = "第二轮普通回答。"
        SequenceProvider.answers = [candidate, fallback]

        message = await self.generate()
        emitted = "".join(data.get("text", "") for kind, data in message.events if kind == "delta")

        self.assertEqual(message.status, "done")
        self.assertEqual(len(SequenceProvider.calls), 2)
        self.assertNotIn(candidate, emitted)
        self.assertEqual(message.content, fallback)
        self.assertEqual(message.settings["knowledge_grounding"], "unverified")
        self.assertIn(chat.KNOWLEDGE_CITATION_WARNING, message.warnings)
        self.assertNotIn("<reference_data>", SequenceProvider.calls[-1][-1]["content"])
        self.assertEqual([item["referenceId"] for item in message.references], ["1"])

    async def test_valid_citation_is_grounded_with_one_model_call(self):
        SequenceProvider.answers = ["有证据的回答 [1]。"]

        message = await self.generate()
        metas = [data for kind, data in message.events if kind == "meta"]

        self.assertEqual(message.status, "done")
        self.assertEqual(len(SequenceProvider.calls), 1)
        self.assertEqual(message.settings["knowledge_grounding"], "grounded")
        self.assertTrue(any(data.get("knowledge_grounding") == "grounded" for data in metas))
        self.assertTrue(any(data.get("read_count") == 1 for data in metas))

    async def test_explicit_stop_keeps_partial_candidate_for_resume(self):
        yielded = asyncio.Event()

        class SlowProvider(SequenceProvider):
            async def stream(self, messages, model, mode):
                self.calls.append(messages)
                yield {"text": "用户主动停止前的部分回答"}
                yielded.set()
                await asyncio.Event().wait()

        body = CreateSessionBody.model_validate({
            "question": "用一句话解释 Transformer。",
            "capabilities": {"knowledge": {"enabled": True}},
        })
        message = await chat.prepare_message(body, OWNER_KEY)
        with patch.object(chat, "ModelProvider", SlowProvider):
            message.task = asyncio.create_task(chat.generate(message))
            await asyncio.wait_for(yielded.wait(), 1)
            await chat.stop_message(message)

        self.assertEqual(message.status, "stopped")
        self.assertEqual(message.content, "用户主动停止前的部分回答")
        self.assertEqual(message.settings["knowledge_grounding"], "unverified")

    async def test_knowledge_off_remains_ordinary_without_grounding_metadata(self):
        SequenceProvider.answers = ["普通回答，无需引用。"]

        body = CreateSessionBody.model_validate({
            "question": "用一句话解释 Transformer。",
            "capabilities": {"knowledge": {"enabled": False}},
        })
        message = await chat.prepare_message(body, OWNER_KEY)
        await chat.generate(message)

        self.assertEqual(message.status, "done", repr(message.events))
        self.assertEqual(len(self.knowledge.calls), 0)
        self.assertEqual(len(SequenceProvider.calls), 1)
        self.assertNotIn("knowledge_grounding", message.settings)


if __name__ == "__main__":
    unittest.main()
