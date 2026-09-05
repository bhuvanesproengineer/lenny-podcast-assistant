import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import SQLAlchemyError

from app.models.db_models import Session, Message
from app.services.session_service import (
    SessionService,
    SessionServiceError,
    SessionNotFoundError,
    InvalidRoleError,
    EmptyMessageError,
    create_session,
    get_session,
    list_sessions,
    add_message,
    get_session_messages,
    update_session_title,
    delete_session,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.mark.anyio
async def test_create_session_default_title(mock_db):
    """Test creating a session with default title."""
    session = await create_session(mock_db)

    assert session.title == "New Chat"
    assert session.id is not None
    assert len(session.id) == 36  # UUID format
    mock_db.add.assert_called_once_with(session)
    mock_db.commit.assert_awaited_once()
    mock_db.refresh.assert_awaited_once_with(session)


@pytest.mark.anyio
async def test_create_session_custom_title(mock_db):
    """Test creating a session with a custom specified title."""
    custom_title = "Product Strategy Discussion"
    session = await create_session(mock_db, title=custom_title)

    assert session.title == custom_title
    mock_db.add.assert_called_once_with(session)
    mock_db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_create_session_db_error_handling(mock_db):
    """Test error handling and rollback when database fails during session creation."""
    mock_db.commit.side_effect = SQLAlchemyError("Connection failed")

    with pytest.raises(SessionServiceError, match="Database error while creating session"):
        await create_session(mock_db, title="Test")

    mock_db.rollback.assert_awaited_once()


@pytest.mark.anyio
async def test_get_session_found(mock_db):
    """Test fetching an existing session."""
    existing_session = Session(id="test-uuid-123", title="Existing Chat")
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_session
    mock_db.execute.return_value = mock_result

    result = await get_session(mock_db, "test-uuid-123")

    assert result is not None
    assert result.id == "test-uuid-123"
    assert result.title == "Existing Chat"


@pytest.mark.anyio
async def test_get_session_not_found(mock_db):
    """Test fetching a non-existent session returns None."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    result = await get_session(mock_db, "nonexistent-id")
    assert result is None


@pytest.mark.anyio
async def test_get_session_invalid_input(mock_db):
    """Test fetching with empty or whitespace session_id returns None without DB call."""
    assert await get_session(mock_db, "") is None
    assert await get_session(mock_db, "   ") is None
    mock_db.execute.assert_not_called()


@pytest.mark.anyio
async def test_list_sessions(mock_db):
    """Test listing sessions with pagination."""
    s1 = Session(id="s1", title="Chat 1")
    s2 = Session(id="s2", title="Chat 2")
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [s1, s2]
    mock_db.execute.return_value = mock_result

    sessions = await list_sessions(mock_db, skip=0, limit=10)

    assert len(sessions) == 2
    assert sessions[0].id == "s1"
    assert sessions[1].id == "s2"
    mock_db.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_add_message_user_and_assistant(mock_db):
    """Test storing user and assistant messages for an active session."""
    active_session = Session(id="session-456", title="Growth Chat")

    # Mock finding the session
    mock_find_res = MagicMock()
    mock_find_res.scalars.return_value.first.return_value = active_session
    mock_db.execute.return_value = mock_find_res

    # 1. Add user message
    user_msg = await add_message(
        mock_db,
        session_id="session-456",
        role="user",
        content="How do I improve onboarding retention?"
    )

    assert user_msg.session_id == "session-456"
    assert user_msg.role == "user"
    assert user_msg.content == "How do I improve onboarding retention?"
    mock_db.add.assert_called()
    mock_db.commit.assert_awaited()

    # 2. Add assistant message (testing case insensitivity)
    asst_msg = await add_message(
        mock_db,
        session_id="session-456",
        role="ASSISTANT",
        content="Focus on time-to-value in the first session."
    )

    assert asst_msg.session_id == "session-456"
    assert asst_msg.role == "assistant"
    assert asst_msg.content == "Focus on time-to-value in the first session."


@pytest.mark.anyio
async def test_add_message_invalid_role(mock_db):
    """Test that invalid roles are rejected."""
    with pytest.raises(InvalidRoleError, match="Invalid role 'system'"):
        await add_message(mock_db, session_id="s1", role="system", content="System instruction")

    with pytest.raises(InvalidRoleError):
        await add_message(mock_db, session_id="s1", role="", content="Hello")


@pytest.mark.anyio
async def test_add_message_empty_content(mock_db):
    """Test that empty or whitespace content is rejected."""
    with pytest.raises(EmptyMessageError, match="Message content cannot be empty"):
        await add_message(mock_db, session_id="s1", role="user", content="   ")

    with pytest.raises(EmptyMessageError):
        await add_message(mock_db, session_id="s1", role="assistant", content="")


@pytest.mark.anyio
async def test_add_message_nonexistent_session(mock_db):
    """Test that adding a message to a non-existent session raises SessionNotFoundError."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(SessionNotFoundError, match="Session 'ghost-session' does not exist"):
        await add_message(mock_db, session_id="ghost-session", role="user", content="Hello?")


@pytest.mark.anyio
async def test_get_session_messages_chronological_order(mock_db):
    """Test retrieving conversation history in chronological order."""
    session = Session(id="session-chrono", title="Chrono Chat")
    
    # 1st call: find session -> returns session
    # 2nd call: select messages -> returns ordered messages
    now = datetime.now(timezone.utc)
    m1 = Message(id=1, session_id="session-chrono", role="user", content="Question 1", created_at=now)
    m2 = Message(id=2, session_id="session-chrono", role="assistant", content="Answer 1", created_at=now + timedelta(seconds=5))
    m3 = Message(id=3, session_id="session-chrono", role="user", content="Follow-up question", created_at=now + timedelta(seconds=10))

    mock_session_res = MagicMock()
    mock_session_res.scalars.return_value.first.return_value = session

    mock_msg_res = MagicMock()
    mock_msg_res.scalars.return_value.all.return_value = [m1, m2, m3]

    mock_db.execute.side_effect = [mock_session_res, mock_msg_res]

    messages = await get_session_messages(mock_db, "session-chrono")

    assert len(messages) == 3
    assert [m.id for m in messages] == [1, 2, 3]
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[2].role == "user"
    assert messages[0].content == "Question 1"
    assert messages[1].content == "Answer 1"
    assert messages[2].content == "Follow-up question"


@pytest.mark.anyio
async def test_get_session_messages_nonexistent_session(mock_db):
    """Test retrieving messages for a non-existent session raises SessionNotFoundError."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(SessionNotFoundError, match="Session 'missing-session' does not exist"):
        await get_session_messages(mock_db, "missing-session")


@pytest.mark.anyio
async def test_multiple_independent_sessions_isolation(mock_db):
    """Test that conversation histories for multiple independent sessions remain isolated."""
    sA = Session(id="session-A", title="Session A")
    sB = Session(id="session-B", title="Session B")

    msg_A = Message(id=1, session_id="session-A", role="user", content="Message for A")
    msg_B = Message(id=2, session_id="session-B", role="user", content="Message for B")

    # When querying session-A
    mock_db.execute.side_effect = [
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sA)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[msg_A])))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=sB)))),
        MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[msg_B])))),
    ]

    history_A = await get_session_messages(mock_db, "session-A")
    assert len(history_A) == 1
    assert history_A[0].content == "Message for A"
    assert history_A[0].session_id == "session-A"

    history_B = await get_session_messages(mock_db, "session-B")
    assert len(history_B) == 1
    assert history_B[0].content == "Message for B"
    assert history_B[0].session_id == "session-B"


@pytest.mark.anyio
async def test_update_session_title_success(mock_db):
    """Test successfully renaming a session."""
    session = Session(id="test-session-1", title="Old Title")
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = session
    mock_db.execute.return_value = mock_result

    updated = await update_session_title(mock_db, "test-session-1", "New Renamed Title")
    assert updated.title == "New Renamed Title"
    mock_db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_update_session_title_not_found(mock_db):
    """Test renaming a non-existent session raises SessionNotFoundError."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(SessionNotFoundError):
        await update_session_title(mock_db, "missing-id", "New Title")


@pytest.mark.anyio
async def test_delete_session_success(mock_db):
    """Test successfully deleting a session."""
    session = Session(id="test-session-del", title="To Delete")
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = session
    mock_db.execute.return_value = mock_result

    result = await delete_session(mock_db, "test-session-del")
    assert result is True
    mock_db.delete.assert_awaited_once_with(session)
    mock_db.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_delete_session_not_found(mock_db):
    """Test deleting a non-existent session raises SessionNotFoundError."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(SessionNotFoundError):
        await delete_session(mock_db, "missing-id")
