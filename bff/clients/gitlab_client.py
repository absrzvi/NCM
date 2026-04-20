"""GitLab client wrapper using python-gitlab (D6)."""
import logging
from functools import lru_cache
from typing import Any

import gitlab
import gitlab.exceptions
from fastapi import HTTPException

from bff.config import settings

logger = logging.getLogger(__name__)

# Max connections for the underlying urllib3 pool used by python-gitlab
_POOL_MAXSIZE = 10
_TIMEOUT = 10


def _get_client() -> gitlab.Gitlab:
    """Return a configured python-gitlab client (singleton via lru_cache)."""
    return _cached_client()


@lru_cache(maxsize=1)
def _cached_client() -> gitlab.Gitlab:
    gl = gitlab.Gitlab(
        url=settings.gitlab_url,
        private_token=settings.gitlab_token,
        timeout=_TIMEOUT,
        session=None,  # let python-gitlab create its own session
    )
    # python-gitlab uses requests internally; set pool size via keep_alive session
    import requests
    from requests.adapters import HTTPAdapter

    adapter = HTTPAdapter(pool_maxsize=_POOL_MAXSIZE)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    gl._session = session  # type: ignore[attr-defined]
    return gl


def _wrap(fn: Any, service: str = "GitLab") -> Any:
    """Execute fn(), converting GitlabError → HTTPException(502)."""
    try:
        return fn()
    except gitlab.exceptions.GitlabAuthenticationError:
        logger.error("GitLab authentication failure")
        raise HTTPException(status_code=502, detail=f"Downstream error: {service} authentication failed")
    except gitlab.exceptions.GitlabGetError as exc:
        logger.error("GitLab get error: %s", exc.error_message)
        raise HTTPException(status_code=502, detail=f"Downstream error: {service} not found")
    except gitlab.exceptions.GitlabTimeoutError:
        logger.error("GitLab request timed out")
        raise HTTPException(status_code=502, detail=f"Downstream error: {service} timeout")
    except gitlab.exceptions.GitlabError as exc:
        logger.error("GitLab error: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"Downstream error: {service} unavailable")


async def get_file(project_id: int, file_path: str, ref: str) -> str:
    """Return decoded file content from GitLab."""
    gl = _get_client()

    def _fetch() -> str:
        project = gl.projects.get(project_id)
        f = project.files.get(file_path=file_path, ref=ref)
        return f.decode().decode("utf-8")

    return _wrap(_fetch)


async def write_file(
    project_id: int,
    file_path: str,
    content: str,
    branch: str,
    commit_message: str,
) -> None:
    """Create or update a file on the given branch."""
    gl = _get_client()

    def _write() -> None:
        project = gl.projects.get(project_id)
        try:
            existing = project.files.get(file_path=file_path, ref=branch)
            existing.content = content
            existing.save(branch=branch, commit_message=commit_message)
        except gitlab.exceptions.GitlabGetError:
            project.files.create(
                {
                    "file_path": file_path,
                    "branch": branch,
                    "content": content,
                    "commit_message": commit_message,
                }
            )

    _wrap(_write)


async def create_branch(project_id: int, branch: str, ref: str) -> None:
    """Create a new branch from ref."""
    gl = _get_client()

    def _create() -> None:
        project = gl.projects.get(project_id)
        project.branches.create({"branch": branch, "ref": ref})

    _wrap(_create)


async def create_mr(
    project_id: int,
    source_branch: str,
    target_branch: str,
    title: str,
    description: str = "",
) -> dict:
    """Create a merge request and return its attributes."""
    gl = _get_client()

    def _create() -> dict:
        project = gl.projects.get(project_id)
        mr = project.mergerequests.create(
            {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
            }
        )
        return {"iid": mr.iid, "web_url": mr.web_url, "state": mr.state}

    return _wrap(_create)


async def list_commits(project_id: int, ref: str, path: str | None = None) -> list[dict]:
    """Return commits for ref, optionally scoped to path."""
    gl = _get_client()

    def _list() -> list[dict]:
        project = gl.projects.get(project_id)
        kwargs: dict = {"ref_name": ref, "all": False}
        if path:
            kwargs["path"] = path
        commits = project.commits.list(**kwargs)
        return [
            {
                "id": c.id,
                "short_id": c.short_id,
                "title": c.title,
                "author_name": c.author_name,
                "created_at": c.created_at,
            }
            for c in commits
        ]

    return _wrap(_list)
