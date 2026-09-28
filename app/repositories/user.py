"""Data access for :class:`~app.models.user.User`."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Encapsulates all persistence operations for users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by (normalized) email address."""
        statement = select(User).where(User.email == email.lower())
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def get(self, user_id: object) -> User | None:
        """Fetch a user by primary key."""
        return await self._session.get(User, user_id)

    async def create(self, email: str, password_hash: str) -> User:
        """Insert a new user.

        Raises :class:`sqlalchemy.exc.IntegrityError` if the email is already
        registered (unique index ``ix_users_email``); the service layer maps
        this to HTTP 409. The flush runs inside a savepoint so a constraint
        violation only rolls back the insert, not any surrounding
        transaction.
        """
        user = User(email=email.lower(), password_hash=password_hash)
        async with self._session.begin_nested():
            self._session.add(user)
            await self._session.flush()
        await self._session.refresh(user)
        return user
