from __future__ import annotations

import asyncio
import unittest

from app.services.agent_runtime import watchers


class _FakeSessionService:
    def __init__(self) -> None:
        self.events = [
            {
                "seq": 1,
                "event_type": "agent_core.final_answer",
                "payload": {"final_answer": "done"},
            }
        ]

    def list_events(self, session_id: str):  # noqa: ARG002
        return list(self.events)


class AgentRuntimeWatchersTest(unittest.TestCase):
    def tearDown(self) -> None:
        watchers._ACTIVE_STREAMS_BY_SESSION.clear()
        watchers._STREAM_OPEN_TIMES_BY_SESSION.clear()

    def test_iter_session_events_emits_stored_events(self) -> None:
        async def run() -> list[str]:
            stream = watchers.iter_session_events(
                service=_FakeSessionService(),
                session_id="as-test",
                since_seq=0,
                poll_seconds=0.2,
                max_seconds=5,
            )
            chunks = []
            async for chunk in stream:
                chunks.append(chunk)
                if len(chunks) >= 3:
                    break
            await stream.aclose()
            return chunks

        chunks = asyncio.run(run())
        joined = "".join(chunks)

        self.assertIn("event: agent_core.final_answer", joined)
        self.assertIn('"final_answer": "done"', joined)

    def test_iter_session_events_throttles_duplicate_session_streams(self) -> None:
        async def run() -> str:
            service = _FakeSessionService()
            first = watchers.iter_session_events(service=service, session_id="as-busy", since_seq=1, max_seconds=5)
            second = watchers.iter_session_events(service=service, session_id="as-busy", since_seq=1, max_seconds=5)
            third = watchers.iter_session_events(service=service, session_id="as-busy", since_seq=1, max_seconds=5)
            await first.__anext__()
            await second.__anext__()
            first_third_chunk = await third.__anext__()
            await first.aclose()
            await second.aclose()
            await third.aclose()
            return first_third_chunk

        first_third_chunk = asyncio.run(run())

        self.assertIn("retry: 30000", first_third_chunk)

    def test_iter_session_events_throttles_reopen_bursts(self) -> None:
        async def run() -> str:
            service = _FakeSessionService()
            latest_chunk = ""
            for _ in range(watchers._MAX_STREAM_OPENS_PER_WINDOW + 1):
                stream = watchers.iter_session_events(service=service, session_id="as-burst", since_seq=1, max_seconds=5)
                latest_chunk = await stream.__anext__()
                await stream.aclose()
            return latest_chunk

        latest_chunk = asyncio.run(run())

        self.assertIn("retry: 30000", latest_chunk)


if __name__ == "__main__":
    unittest.main()
