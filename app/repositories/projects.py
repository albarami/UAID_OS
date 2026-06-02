"""Tenant-scoped CRUD for ``projects``."""

from app.models.project import Project
from app.tenancy import TenantContext, TenantScopedRepository
from sqlalchemy.ext.asyncio import AsyncSession


class ProjectRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession, context: TenantContext):
        super().__init__(session, context, Project)

    async def create(self, *, name: str, slug: str) -> Project:
        project = Project(name=name, slug=slug)
        return await self.add(project)
