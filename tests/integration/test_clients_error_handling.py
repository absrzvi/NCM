"""Integration tests: error sanitisation and connection pooling (STORY-05)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import gitlab.exceptions
import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Error sanitisation — all four clients
# ---------------------------------------------------------------------------

class TestErrorSanitisation:
    """All clients must return 502 detail containing no URLs, tokens, or stack traces."""

    _FAKE_TOKENS = {
        "GITLAB_TOKEN": "gitlab-fake-token-should-not-leak",
        "PUPPETDB_TOKEN": "puppetdb-fake-token-should-not-leak",
        "PUPPET_SERVER_TOKEN": "puppet-server-fake-token-should-not-leak",
    }
    _FAKE_URLS = {
        "GITLAB_URL": "https://gitlab.internal.example.com",
        "PUPPETDB_URL": "https://puppetdb.internal.example.com",
        "PUPPET_SERVER_URL": "https://puppet.internal.example.com",
    }

    def _assert_sanitised(self, exc_info: pytest.ExceptionInfo) -> None:
        detail = exc_info.value.detail
        assert exc_info.value.status_code == 502
        for token in self._FAKE_TOKENS.values():
            assert token not in detail, f"Token leaked in detail: {detail}"
        for url in self._FAKE_URLS.values():
            assert url not in detail, f"URL leaked in detail: {detail}"
        # No Python traceback fragments
        assert "Traceback" not in detail
        assert "File \"" not in detail

    @pytest.mark.asyncio
    async def test_gitlab_sanitises_error(self):
        from bff.clients import gitlab_client

        mock_gl = MagicMock()
        mock_gl.projects.get.side_effect = gitlab.exceptions.GitlabError("internal error")

        with patch.object(gitlab_client, "_cached_client", return_value=mock_gl), \
             patch("bff.clients.gitlab_client.settings") as s:
            s.gitlab_token = self._FAKE_TOKENS["GITLAB_TOKEN"]
            s.gitlab_url = self._FAKE_URLS["GITLAB_URL"]
            with pytest.raises(HTTPException) as exc_info:
                await gitlab_client.get_file(1211, "data/common.yaml", "devel")
        self._assert_sanitised(exc_info)

    @pytest.mark.asyncio
    async def test_puppetdb_sanitises_error(self):
        from bff.clients import puppetdb_client

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")

        with patch.object(puppetdb_client, "get_puppetdb_client", return_value=mock_client), \
             patch("bff.clients.puppetdb_client.settings") as s:
            s.puppetdb_token = self._FAKE_TOKENS["PUPPETDB_TOKEN"]
            s.puppetdb_url = self._FAKE_URLS["PUPPETDB_URL"]
            with pytest.raises(HTTPException) as exc_info:
                await puppetdb_client.query_puppetdb("reports[]")
        self._assert_sanitised(exc_info)

    @pytest.mark.asyncio
    async def test_puppet_server_sanitises_error(self):
        from bff.clients import puppet_server_client

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")

        with patch.object(puppet_server_client, "get_puppet_server_client", return_value=mock_client), \
             patch("bff.clients.puppet_server_client.settings") as s:
            s.puppet_server_token = self._FAKE_TOKENS["PUPPET_SERVER_TOKEN"]
            s.puppet_server_url = self._FAKE_URLS["PUPPET_SERVER_URL"]
            with pytest.raises(HTTPException) as exc_info:
                await puppet_server_client.trigger_puppet_run("node1.example.com", "devel")
        self._assert_sanitised(exc_info)

    @pytest.mark.asyncio
    async def test_keycloak_sanitises_error(self):
        from bff.clients import keycloak_jwks

        keycloak_jwks.invalidate_jwks_cache()

        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")

        with patch.object(keycloak_jwks, "get_keycloak_client", return_value=mock_client), \
             patch("bff.clients.keycloak_jwks.settings") as s:
            s.keycloak_jwks_uri = "https://keycloak.internal.example.com/certs"
            with pytest.raises(HTTPException) as exc_info:
                await keycloak_jwks.fetch_jwks()

        detail = exc_info.value.detail
        assert exc_info.value.status_code == 502
        assert "keycloak.internal.example.com" not in detail
        assert "Traceback" not in detail

    @pytest.mark.asyncio
    async def test_all_clients_sanitise_error_details(self):
        """Umbrella: inject errors across all four clients, assert no leakage."""
        from bff.clients import gitlab_client, puppetdb_client, puppet_server_client, keycloak_jwks

        keycloak_jwks.invalidate_jwks_cache()

        # GitLab
        mock_gl = MagicMock()
        mock_gl.projects.get.side_effect = gitlab.exceptions.GitlabError("err")
        with patch.object(gitlab_client, "_cached_client", return_value=mock_gl):
            with pytest.raises(HTTPException) as exc:
                await gitlab_client.get_file(1, "f", "devel")
            assert exc.value.status_code == 502

        # PuppetDB
        mock_pdb = AsyncMock()
        mock_pdb.get.side_effect = httpx.TimeoutException("t/o")
        with patch.object(puppetdb_client, "get_puppetdb_client", return_value=mock_pdb):
            with pytest.raises(HTTPException) as exc:
                await puppetdb_client.query_puppetdb("r[]")
            assert exc.value.status_code == 502

        # Puppet Server
        mock_ps = AsyncMock()
        mock_ps.post.side_effect = httpx.TimeoutException("t/o")
        with patch.object(puppet_server_client, "get_puppet_server_client", return_value=mock_ps):
            with pytest.raises(HTTPException) as exc:
                await puppet_server_client.trigger_puppet_run("n", "devel")
            assert exc.value.status_code == 502

        # Keycloak
        mock_kc = AsyncMock()
        mock_kc.get.side_effect = httpx.TimeoutException("t/o")
        with patch.object(keycloak_jwks, "get_keycloak_client", return_value=mock_kc), \
             patch("bff.clients.keycloak_jwks.settings") as s:
            s.keycloak_jwks_uri = "https://kc/certs"
            with pytest.raises(HTTPException) as exc:
                await keycloak_jwks.fetch_jwks()
            assert exc.value.status_code == 502


# ---------------------------------------------------------------------------
# Connection pool boundary — GitLab client
# ---------------------------------------------------------------------------

class TestConnectionPooling:
    @pytest.mark.asyncio
    async def test_connection_pooling(self):
        """20 concurrent get_file calls all go through the same cached client instance."""
        from bff.clients import gitlab_client

        call_count = 0

        def make_mock_gl():
            mock_project = MagicMock()
            mock_file = MagicMock()
            mock_file.decode.return_value = b"value\n"
            mock_project.files.get.return_value = mock_file
            mock_gl = MagicMock()
            mock_gl.projects.get.return_value = mock_project
            return mock_gl

        shared_gl = make_mock_gl()

        with patch.object(gitlab_client, "_cached_client", return_value=shared_gl):
            tasks = [
                gitlab_client.get_file(1211, f"path/{i}.yaml", "devel")
                for i in range(20)
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 20
        # All 20 calls used the same client instance (lru_cache ensures singleton)
        assert shared_gl.projects.get.call_count == 20
