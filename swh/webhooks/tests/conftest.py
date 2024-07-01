# Copyright (C) 2023-2024  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information


import json
import os
from pathlib import Path
import shutil
from subprocess import CalledProcessError, check_output, run

import netifaces
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from swh.webhooks.interface import EventType

_SVIX_ORG_ID = "org_swh_webhooks"
_svix_auth_token = None


def pytest_collection_modifyitems(config, items):
    """Tests for swh-webhooks require docker compose (v2 or v1) so skip them
    if it is not installed on host."""
    skipper = None
    if shutil.which("docker") is None:
        skipper = pytest.mark.skip(reason="skipping test as docker command is missing")
    else:
        docker_compose_available = False
        try:
            # check if docker compose v2 if available
            check_output(["docker", "compose", "version"])
            docker_compose_available = True
        except CalledProcessError:
            # check if docker compose v1 if available
            docker_compose_available = shutil.which("docker-compose") is not None
        finally:
            if not docker_compose_available:
                skipper = pytest.mark.skip(
                    reason="skipping test as docker compose is missing"
                )
    if skipper is not None:
        for item in items:
            item.add_marker(skipper)


@pytest.fixture(autouse=True, scope="session")
def docker_pull_svix_image():
    """Ensure to use latest svix/svix-server docker image"""
    run(["docker", "pull", "svix/svix-server"], cwd=os.path.dirname(__file__))


@pytest.fixture(scope="session")
def docker_compose_command():
    try:
        # use docker compose v2 if available
        check_output(["docker", "compose", "version"])
        return "docker compose"
    except Exception:
        # fallback on v1 otherwise
        return "docker-compose"


@pytest.fixture(scope="session")
def docker_compose_file():
    return os.path.join(os.path.dirname(__file__), "docker-compose.yml")


@pytest.fixture(scope="session")
def docker_compose(docker_services):
    return docker_services._docker_compose


@pytest.fixture(scope="session")
def svix_server_url(docker_services):
    # svix server container exposes a free port to the docker host,
    # we use the docker network gateway IP in case the tests are also
    # executed in a container (as in SWH Jenkins)
    svix_server_port = docker_services.port_for("svix-backend", 8071)
    return f"http://172.17.0.1:{svix_server_port}"


@pytest.fixture(autouse=True, scope="session")
def svix_server(docker_compose, svix_server_url):
    """Spawn a Svix server for the tests session using docker-compose"""
    global _svix_auth_token

    # wait for the svix backend service to be up and responding
    request_session = requests.Session()
    retries = Retry(total=10, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    request_session.mount("http://", HTTPAdapter(max_retries=retries))
    api_url = f"{svix_server_url}/api/v1/health/"
    response = request_session.get(api_url)
    assert response

    # generate bearer token to authorize communication with the svix server
    exec_output = docker_compose.execute(
        f"exec -T svix-backend svix-server jwt generate {_SVIX_ORG_ID}"
    )
    _svix_auth_token = (
        exec_output.decode()
        .replace("Token (Bearer): ", "")
        .replace("\r", "")
        .replace("\n", "")
    )


@pytest.fixture(autouse=True)
def svix_wiper(docker_compose):
    """Ensure stateless tests"""
    yield
    # wipe svix database after each test to ensure stateless tests
    docker_compose.execute(
        f"exec -T svix-backend svix-server wipe --yes-i-know-what-im-doing {_SVIX_ORG_ID}"
    )


def _httpserver_ip_address():
    for interface in netifaces.interfaces():
        for address in netifaces.ifaddresses(interface).get(netifaces.AF_INET, []):
            server_ip_adress = address.get("addr", "")
            if server_ip_adress.startswith("172.17.0."):
                return server_ip_adress


@pytest.fixture(scope="session")
def httpserver_listen_address():
    # Use IP address in the docker bridge network as server hostname in order for
    # the svix server executed in a docker container to successfully send webhooks
    # to the HTTP server executed on the host
    httpserver_ip_address = _httpserver_ip_address()
    assert httpserver_ip_address
    return (httpserver_ip_address, 0)


@pytest.fixture
def svix_auth_token():
    return _svix_auth_token


@pytest.fixture
def swh_webhooks(svix_server_url, svix_auth_token):
    from swh.webhooks.interface import Webhooks

    return Webhooks(svix_server_url=svix_server_url, svix_auth_token=svix_auth_token)


@pytest.fixture
def origin_create_event_type(datadir):
    return EventType(
        name="origin.create",
        description=(
            "This event is triggered when a new software origin is added to the archive"
        ),
        schema=json.loads(Path(datadir, "origin_create.json").read_text()),
    )


@pytest.fixture
def origin_visit_event_type(datadir):
    return EventType(
        name="origin.visit",
        description=(
            "This event is triggered when a new visit of a software origin was performed"
        ),
        schema=json.loads(Path(datadir, "origin_visit.json").read_text()),
    )


@pytest.fixture(autouse=True)
def mock_sleep(mocker):
    return mocker.patch("time.sleep")
