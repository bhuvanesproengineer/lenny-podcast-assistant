import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import get_db
from app.api.chat import get_rag_service, get_lenny_agent
from app.models.db_models import Session, Message
from app.rag.retriever import RAGResponse
from app.agent.tools import AgentResponse
from app.services.session_service import SessionNotFoundError, SessionServiceError


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def mock_rag():
    rag = MagicMock()
    rag.answer = AsyncMock()
    return rag


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.run = AsyncMock()
    return agent


@pytest.mark.anyio
async def test_health_check_success():
    with patch("app.api.health.check_db_connection", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (True, None)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {
                "status": "healthy",
                "database": "connected"
            }


@pytest.mark.anyio
async def test_health_check_failure():
    with patch("app.api.health.check_db_connection", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = (False, "Connection timeout")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 503
            assert response.json() == {
                "status": "unhealthy",
                "database": "disconnected",
                "error": "Connection timeout"
            }


@pytest.mark.anyio
async def test_post_session_new_default(mock_db):
    fake_session = Session(id="uuid-session-1", title="New Chat")

    with patch("app.api.sessions.SessionService.create_session", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = fake_session
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/session/new", json={})
                assert response.status_code == 201
                data = response.json()
                assert data["session_id"] == "uuid-session-1"
                assert data["title"] == "New Chat"
                mock_create.assert_awaited_once_with(mock_db, title=None)
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_post_session_new_custom_title(mock_db):
    fake_session = Session(id="uuid-session-2", title="Growth Hacks")

    with patch("app.api.sessions.SessionService.create_session", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = fake_session
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/session/new", json={"title": "Growth Hacks"})
                assert response.status_code == 201
                data = response.json()
                assert data["session_id"] == "uuid-session-2"
                assert data["title"] == "Growth Hacks"
                mock_create.assert_awaited_once_with(mock_db, title="Growth Hacks")
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_get_sessions_list(mock_db):
    now = datetime.now(timezone.utc)
    s1 = Session(id="s1", title="Chat 1", created_at=now, updated_at=now)
    s2 = Session(id="s2", title="Chat 2", created_at=now, updated_at=now)

    with patch("app.api.sessions.SessionService.list_sessions", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [s1, s2]
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/sessions?skip=0&limit=10")
                assert response.status_code == 200
                data = response.json()
                assert len(data) == 2
                assert data[0]["id"] == "s1"
                assert data[1]["id"] == "s2"
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_get_session_details_success(mock_db):
    now = datetime.now(timezone.utc)
    s = Session(id="s-detail", title="Detail Chat", created_at=now, updated_at=now)
    m1 = Message(id=1, session_id="s-detail", role="user", content="Hi", created_at=now)
    m2 = Message(id=2, session_id="s-detail", role="assistant", content="Hello!", created_at=now)

    with patch("app.api.sessions.SessionService.get_session", new_callable=AsyncMock) as mock_get, \
         patch("app.api.sessions.SessionService.get_session_messages", new_callable=AsyncMock) as mock_msgs:
        mock_get.return_value = s
        mock_msgs.return_value = [m1, m2]
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/sessions/s-detail")
                assert response.status_code == 200
                data = response.json()
                assert data["id"] == "s-detail"
                assert data["title"] == "Detail Chat"
                assert len(data["messages"]) == 2
                assert data["messages"][0]["role"] == "user"
                assert data["messages"][1]["role"] == "assistant"
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_get_session_details_not_found(mock_db):
    with patch("app.api.sessions.SessionService.get_session", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/sessions/missing-id")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_chat_success(mock_db, mock_agent):
    fake_session = Session(id="sess-chat-1", title="Chat Session")
    mock_agent.run.return_value = AgentResponse(
        selected_tool="PodcastRAGTool",
        answer="According to Dalton Caldwell, you should talk directly to early users.",
        sources=["Lessons from 1,000+ YC startups | Dalton Caldwell"]
    )

    with patch("app.api.chat.SessionService.get_session", new_callable=AsyncMock) as mock_get_sess, \
         patch("app.api.chat.SessionService.add_message", new_callable=AsyncMock) as mock_add_msg:
        mock_get_sess.return_value = fake_session
        mock_add_msg.return_value = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_lenny_agent] = lambda: mock_agent
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                payload = {
                    "session_id": "sess-chat-1",
                    "message": "How do startups get customers?"
                }
                response = await client.post("/chat", json=payload)
                assert response.status_code == 200
                data = response.json()
                assert data["session_id"] == "sess-chat-1"
                assert "Dalton Caldwell" in data["answer"]
                assert data["sources"] == ["Lessons from 1,000+ YC startups | Dalton Caldwell"]
                assert data["selected_tool"] == "PodcastRAGTool"

                # Verify user message stored
                assert mock_add_msg.await_count == 2
                first_call = mock_add_msg.await_args_list[0]
                assert first_call.kwargs["role"] == "user"
                assert first_call.kwargs["content"] == "How do startups get customers?"

                # Verify assistant message stored
                second_call = mock_add_msg.await_args_list[1]
                assert second_call.kwargs["role"] == "assistant"
                assert "Dalton Caldwell" in second_call.kwargs["content"]
                mock_agent.run.assert_awaited_once_with("How do startups get customers?")
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_chat_ship30_tool_invocation(mock_db, mock_agent):
    """Verifies that Ship30 requests flow through LennyAgent and return selected_tool='Ship30Tool'."""
    fake_session = Session(id="sess-ship30", title="Ship30 Chat")
    mock_agent.run.return_value = AgentResponse(
        selected_tool="Ship30Tool",
        answer="# The Non-Obvious Truth About Startup Growth\n\nMost founders believe startup growth is linear...",
        sources=["Elena Verna on B2B growth loops | Lenny's Podcast"]
    )

    with patch("app.api.chat.SessionService.get_session", new_callable=AsyncMock) as mock_get_sess, \
         patch("app.api.chat.SessionService.add_message", new_callable=AsyncMock) as mock_add_msg:
        mock_get_sess.return_value = fake_session
        mock_add_msg.return_value = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_lenny_agent] = lambda: mock_agent
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                payload = {
                    "session_id": "sess-ship30",
                    "message": "Write a Ship30 article about startup growth"
                }
                response = await client.post("/chat", json=payload)
                assert response.status_code == 200
                data = response.json()
                assert data["session_id"] == "sess-ship30"
                assert data["selected_tool"] == "Ship30Tool"
                assert "Startup Growth" in data["answer"]
                assert data["sources"] == ["Elena Verna on B2B growth loops | Lenny's Podcast"]
                mock_agent.run.assert_awaited_once_with("Write a Ship30 article about startup growth")
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_chat_session_not_found(mock_db, mock_agent):
    with patch("app.api.chat.SessionService.get_session", new_callable=AsyncMock) as mock_get_sess:
        mock_get_sess.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_lenny_agent] = lambda: mock_agent
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/chat", json={
                    "session_id": "ghost-id",
                    "message": "Hello"
                })
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_chat_empty_message_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Whitespace message
        response = await client.post("/chat", json={
            "session_id": "some-session",
            "message": "    "
        })
        assert response.status_code == 422


@pytest.mark.anyio
async def test_chat_agent_failure(mock_db, mock_agent):
    fake_session = Session(id="sess-fail", title="Fail Chat")
    mock_agent.run.side_effect = RuntimeError("Ollama service down")

    with patch("app.api.chat.SessionService.get_session", new_callable=AsyncMock) as mock_get_sess, \
         patch("app.api.chat.SessionService.add_message", new_callable=AsyncMock) as mock_add_msg:
        mock_get_sess.return_value = fake_session
        mock_add_msg.return_value = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_lenny_agent] = lambda: mock_agent
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/chat", json={
                    "session_id": "sess-fail",
                    "message": "Trigger failure"
                })
                assert response.status_code == 500
                assert "Failed to generate answer from agent" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()
