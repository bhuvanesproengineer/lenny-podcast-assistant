import asyncio
import sys
from pathlib import Path

# Ensure backend directory is in sys.path so app modules can be imported
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import AsyncSessionLocal
from app.services.session_service import SessionService


async def main():
    print("=" * 60)
    print("SessionService Test Script")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # 1. Create a session named "Test Session"
        session = await SessionService.create_session(db, title="Test Session")
        print(f"\nSession Created successfully!")
        print(f"Session ID: {session.id}")
        print(f"Session Title: {session.title}")

        # 2. Add a user message: "Hello"
        user_msg = await SessionService.add_message(
            db=db,
            session_id=session.id,
            role="user",
            content="Hello"
        )
        print(f"\nAdded User Message (ID: {user_msg.id}): '{user_msg.content}'")

        # 3. Add an assistant message: "Hi, how can I help you?"
        asst_msg = await SessionService.add_message(
            db=db,
            session_id=session.id,
            role="assistant",
            content="Hi, how can I help you?"
        )
        print(f"Added Assistant Message (ID: {asst_msg.id}): '{asst_msg.content}'")

        # 4. Retrieve all messages for the session
        messages = await SessionService.get_session_messages(db, session_id=session.id)

        # 5. Print session ID and retrieved messages
        print("\n" + "=" * 60)
        print(f"Retrieved Messages for Session: {session.id}")
        print("=" * 60)
        for idx, msg in enumerate(messages, 1):
            print(f"[{idx}] {msg.role.upper()} ({msg.created_at}): {msg.content}")

        print("=" * 60)
        print("Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
