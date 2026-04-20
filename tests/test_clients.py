"""Unit tests for downstream client wrappers (STORY-05)."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import gitlab.exceptions
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# GitLab client tests
# ---------------------------------------------------------------------------

class TestGitlabClient:
    def test_gitlab_client_success(self):
        """Mock python-gitlab; assert get_file returns expected content."""
        from bff.clients import gitlab_client

        mock_project = MagicMock()
        mock_file = MagicMock()
        mock_file.decode.return_value = b"key: value\n"
        mock_project.files.get.return_value = mock_file

        mock_gl = MagicMock()
        mock_gl.projects.get.return_value = mock_project

        with patch.object(gitlab_client, "_cached_client", return_value=mock_gl):
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                gitlab_client.get_file(1211, "data/common.yaml", "devel")
            )
        assert result == "key: value\n"

    def test_gitlab_client_timeout(self):
        """Mock GitlabTimeoutError → HTTPException(502) with 'timeout' in detail."""
        from bff.clients import gitlab_client

        mock_gl = MagicMock()
        mock_gl.projects.get.side_effect = gitlab.exceptions.GitlabTimeoutError

        with patch.object(gitlab_client, "_cached_client", return_value=mock_gl):
            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    gitlab_client.get_file(1211, "data/common.yaml", "devel")
                )
        assert exc_info.value.status_code == 502
        assert "timeout" in exc_info.value.detail.lower()

    def test_gitlab_client_connection_error(self):
        """Mock GitlabError → HTTPException(502) with sanitised detail."""
        from bff.clients import gitlab_client

        mock_gl = MagicMock()
        mock_gl.projects.get.side_effect = gitlab.exceptions.GitlabError("connection refused")

        with patch.object(gitlab_client, "_cached_client", return_value=mock_gl):
            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    gitlab_client.get_file(1211, "data/common.yaml", "devel")
                )
        assert exc_info.value.status_code == 502
        assert "GitLab" in exc_info.value.detail

    def test_gitlab_client_no_token_in_error(self):
        """Error detail must never contain the GitLab token."""
        from bff.clients import gitlab_client

        mock_gl = MagicMock()
        mock_gl.projects.get.side_effect = gitlab.exceptions.GitlabError("some error")

        with patch.object(gitlab_client, "_cached_client", return_value=mock_gl), \
             patch("bff.clients.gitlab_client.settings") as mock_settings:
            mock_settings.gitlab_token = "super-secret-token-abc123"
            mock_settings.gitlab_url = "https://gitlab.example.com"
            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.get_event_loop().run_until_complete(
                    gitlab_client.get_file(1211, "data/common.yaml", "devel")
                )
        assert "super-secret-token-abc123" not in exc_info.value.detail


# ---------------------------------------------------------------------------
# PuppetDB client tests
# ---------------------------------------------------------------------------

class TestPuppetdbClient:
    @pytest.mark.asyncio
    async def test_puppetdb_client_pql_query(self):
        """Mock httpx GET /pdb/query/v4; assert PQL result parsed correctly."""
        from bff.clients import puppetdb_client

        mock_response = MagicMock()
        mock_response.json.return_value = [{"certname": "node1.example.com", "status": "changed"}]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(puppetdb_client, "get_puppetdb_client", return_value=mock_client):
            result = await puppetdb_client.query_puppetdb('reports[certname]{certname="node1.example.com"}')

        assert len(result) == 1
        assert result[0]["certname"] == "node1.example.com"

    @pytest.mark.asyncio
    async def test_puppetdb_client_timeout(self):
        """Mock TimeoutException → HTTPException(502)."""
        from bff.clients import puppetdb_client

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        with patch.object(puppetdb_client, "get_puppetdb_client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await puppetdb_client.query_puppetdb("reports[]")

        assert exc_info.value.status_code == 502
        assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_puppetdb_client_no_token_in_error(self):
        """Error detail must never contain the PuppetDB token."""
        from bff.clients import puppetdb_client

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")

        with patch.object(puppetdb_client, "get_puppetdb_client", return_value=mock_client), \
             patch("bff.clients.puppetdb_client.settings") as mock_settings:
            mock_settings.puppetdb_token = "puppetdb-secret-token-xyz"
            with pytest.raises(HTTPException) as exc_info:
                await puppetdb_client.query_puppetdb("reports[]")

        assert "puppetdb-secret-token-xyz" not in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_puppetdb_get_node_facts(self):
        """Mock facts endpoint; assert dict is returned."""
        from bff.clients import puppetdb_client

        facts_payload = [
            {"name": "os", "value": "Linux"},
            {"name": "fqdn", "value": "node1.example.com"},
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = facts_payload
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(puppetdb_client, "get_puppetdb_client", return_value=mock_client):
            result = await puppetdb_client.get_node_facts("node1.example.com")

        assert result["os"] == "Linux"
        assert result["fqdn"] == "node1.example.com"


# ---------------------------------------------------------------------------
# Puppet Server client tests
# ---------------------------------------------------------------------------

class TestPuppetServerClient:
    @pytest.mark.asyncio
    async def test_puppet_server_client_run_force(self):
        """Mock POST /run-force; assert run UUID returned."""
        from bff.clients import puppet_server_client

        mock_response = MagicMock()
        mock_response.json.return_value = {"run_id": "abc-123", "status": "accepted"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        with patch.object(puppet_server_client, "get_puppet_server_client", return_value=mock_client):
            result = await puppet_server_client.trigger_puppet_run(
                certname="node1.example.com", environment="devel"
            )

        assert result["run_id"] == "abc-123"
        mock_client.post.assert_called_once_with(
            "/run-force",
            json={"certname": "node1.example.com", "environment": "devel"},
        )

    @pytest.mark.asyncio
    async def test_puppet_server_client_connection_error(self):
        """Mock ConnectError → HTTPException(502) with sanitised detail."""
        from bff.clients import puppet_server_client

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch.object(puppet_server_client, "get_puppet_server_client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await puppet_server_client.trigger_puppet_run("node1.example.com", "devel")

        assert exc_info.value.status_code == 502
        assert "Puppet Server" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_puppet_server_client_timeout(self):
        """Mock TimeoutException → HTTPException(502)."""
        from bff.clients import puppet_server_client

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with patch.object(puppet_server_client, "get_puppet_server_client", return_value=mock_client):
            with pytest.raises(HTTPException) as exc_info:
                await puppet_server_client.trigger_puppet_run("node1.example.com", "devel")

        assert exc_info.value.status_code == 502
        assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_puppet_server_no_token_in_error(self):
        """Error detail must never contain the Puppet Server token."""
        from bff.clients import puppet_server_client

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")

        with patch.object(puppet_server_client, "get_puppet_server_client", return_value=mock_client), \
             patch("bff.clients.puppet_server_client.settings") as mock_settings:
            mock_settings.puppet_server_token = "puppet-server-secret-token"
            with pytest.raises(HTTPException) as exc_info:
                await puppet_server_client.trigger_puppet_run("node1.example.com", "devel")

        assert "puppet-server-secret-token" not in exc_info.value.detail


# ---------------------------------------------------------------------------
# Keycloak JWKS tests
# ---------------------------------------------------------------------------

class TestKeycloakJwks:
    @pytest.mark.asyncio
    async def test_keycloak_jwks_fetch(self):
        """Mock httpx GET; assert JWKS dict returned and cached."""
        from bff.clients import keycloak_jwks

        keycloak_jwks.invalidate_jwks_cache()

        jwks_payload = {"keys": [{"kid": "key1", "kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = jwks_payload
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(keycloak_jwks, "get_keycloak_client", return_value=mock_client), \
             patch("bff.clients.keycloak_jwks.settings") as mock_settings:
            mock_settings.keycloak_jwks_uri = "https://keycloak.example.com/auth/realms/nms/protocol/openid-connect/certs"
            result = await keycloak_jwks.fetch_jwks()

        assert result == jwks_payload
        assert mock_client.get.call_count == 1

        # Second call should use cache (no additional HTTP request)
        with patch.object(keycloak_jwks, "get_keycloak_client", return_value=mock_client):
            result2 = await keycloak_jwks.fetch_jwks()
        assert result2 == jwks_payload
        assert mock_client.get.call_count == 1  # still 1 — served from cache

    @pytest.mark.asyncio
    async def test_keycloak_jwks_timeout(self):
        """Mock TimeoutException → HTTPException(502)."""
        from bff.clients import keycloak_jwks

        keycloak_jwks.invalidate_jwks_cache()

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        with patch.object(keycloak_jwks, "get_keycloak_client", return_value=mock_client), \
             patch("bff.clients.keycloak_jwks.settings") as mock_settings:
            mock_settings.keycloak_jwks_uri = "https://keycloak.example.com/certs"
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_jwks.fetch_jwks()

        assert exc_info.value.status_code == 502
        assert "timeout" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_keycloak_readyz_uses_5s_timeout(self):
        """When fetch_jwks(timeout=5.0) is called, the 5s timeout is forwarded."""
        from bff.clients import keycloak_jwks

        keycloak_jwks.invalidate_jwks_cache()

        jwks_payload = {"keys": []}
        mock_response = MagicMock()
        mock_response.json.return_value = jwks_payload
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch.object(keycloak_jwks, "get_keycloak_client", return_value=mock_client), \
             patch("bff.clients.keycloak_jwks.settings") as mock_settings:
            mock_settings.keycloak_jwks_uri = "https://keycloak.example.com/certs"
            await keycloak_jwks.fetch_jwks(timeout=5.0)

        mock_client.get.assert_called_once_with(
            "https://keycloak.example.com/certs", timeout=5.0
        )
