import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.session_service import (
    SessionService,
    SessionNotFoundError,
    SessionServiceError
)
from app.agent.agent import LennyAgent
from app.agent.tools import AgentResponse
from app.rag.retriever import RAGService
from app.models.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# Default agent and RAG instances
_default_lenny_agent: Optional[LennyAgent] = None
_default_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Dependency provider for RAGService, enabling easy mocking and backward compatibility."""
    global _default_rag_service
    if _default_rag_service is None:
        _default_rag_service = RAGService()
    return _default_rag_service


def get_lenny_agent() -> LennyAgent:
    """Dependency provider for LennyAgent orchestrator, enabling easy mocking and dependency injection."""
    global _default_lenny_agent
    if _default_lenny_agent is None:
        _default_lenny_agent = LennyAgent()
    return _default_lenny_agent


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    agent: LennyAgent = Depends(get_lenny_agent),
):
    """
    Orchestrates the chat interaction through the LennyAgent layer:
    1. Validates that the requested session exists.
    2. Stores the incoming user message.
    3. Invokes LennyAgent to route intent (PodcastRAGTool vs Ship30Tool) and synthesize response.
    4. Stores the generated assistant response.
    5. Returns the answer, source titles, selected_tool, and session ID.
    """
    clean_session_id = payload.session_id.strip()
    user_message = payload.message.strip()

    logger.info(
        "Received /chat request",
        extra={"session_id": clean_session_id, "message_length": len(user_message)}
    )

    # 1. Validate session existence
    session = await SessionService.get_session(db, clean_session_id)
    if session is None:
        logger.warning("Chat request rejected: session not found", extra={"session_id": clean_session_id})
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{clean_session_id}' not found"
        )

    # 2. Store user message
    try:
        await SessionService.add_message(
            db=db,
            session_id=session.id,
            role="user",
            content=user_message
        )
    except SessionServiceError as exc:
        logger.error("Failed to store user message: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store user message"
        ) from exc

    # 3. Retrieve prior conversation history for contextual query rewriting
    chat_history = []
    try:
        past_messages = await SessionService.get_session_messages(db, session.id)
        # Exclude the message just inserted (the last one) so history contains prior context
        chat_history = [
            {"role": m.role, "content": m.content}
            for m in past_messages[:-1]
        ]
    except Exception as exc:
        logger.warning("Could not fetch chat history for session %s: %s", session.id, exc)

    # 4. Route through LennyAgent orchestration layer with conversational context if present
    try:
        if chat_history:
            agent_response = await agent.run(user_message, chat_history=chat_history)
        else:
            agent_response = await agent.run(user_message)
    except Exception as exc:
        logger.error("LennyAgent orchestration error during chat: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate answer from agent: {exc}"
        ) from exc

    # Extract answer, sources, and selected_tool from AgentResponse or dict
    if isinstance(agent_response, dict):
        answer = agent_response.get("answer", "")
        sources = agent_response.get("sources", [])
        selected_tool = agent_response.get("selected_tool", None)
        artifact = bool(agent_response.get("artifact", False))
        markdown_content = agent_response.get("markdown_content", None)
        html_content = agent_response.get("html_content", None)
        word_count = agent_response.get("word_count", None)
    else:
        answer = getattr(agent_response, "answer", str(agent_response))
        sources = getattr(agent_response, "sources", [])
        selected_tool = getattr(agent_response, "selected_tool", None)
        artifact = getattr(agent_response, "artifact", False)
        markdown_content = getattr(agent_response, "markdown_content", None)
        html_content = getattr(agent_response, "html_content", None)
        word_count = getattr(agent_response, "word_count", None)

    if word_count is None and (markdown_content or answer) and artifact:
        word_count = len((markdown_content or answer).strip().split())

    # 4. Store assistant response
    try:
        await SessionService.add_message(
            db=db,
            session_id=session.id,
            role="assistant",
            content=answer
        )
    except SessionServiceError as exc:
        logger.error("Failed to store assistant response: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record assistant message"
        ) from exc

    logger.info(
        "Chat request processed successfully via LennyAgent",
        extra={
            "session_id": session.id,
            "selected_tool": selected_tool,
            "sources_count": len(sources),
            "answer_length": len(answer),
            "artifact": artifact,
            "word_count": word_count,
        }
    )

    # 5. Return structured response with selected_tool and artifact metadata
    return ChatResponse(
        session_id=session.id,
        answer=answer,
        sources=sources,
        selected_tool=selected_tool,
        artifact=artifact,
        markdown_content=markdown_content,
        html_content=html_content,
        word_count=word_count,
    )
