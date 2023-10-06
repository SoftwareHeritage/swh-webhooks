# Copyright (C) 2023  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import os
from subprocess import run

import netifaces
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_SVIX_ORG_ID = "org_swh_webhooks"
# svix server container exposes the 8071 port to the docker host,
# we use the docker network gateway IP in case the tests are also
# executed in a container (as in SWH Jenkins)
_SVIX_SERVER_URL = "http://172.17.0.1:8071"
_svix_service = None
_svix_auth_token = None


@pytest.fixture(autouse=True, scope="session")
def docker_compose_down():
    """Ensure docker services are down and volumes removed prior running tests"""
    run(["docker-compose", "down", "-v"], cwd=os.path.dirname(__file__))


@pytest.fixture(autouse=True, scope="session")
def docker_pull_svix_image():
    """Ensure to use latest svix/svix-server docker image"""
    run(["docker", "pull", "svix/svix-server"], cwd=os.path.dirname(__file__))


@pytest.fixture(autouse=True, scope="session")
def svix_server(session_scoped_container_getter):
    """Spawn a Svix server for the tests session using docker-compose"""
    global _svix_service, _svix_auth_token

    # wait for the svix backend service to be up and responding
    request_session = requests.Session()
    retries = Retry(total=10, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    request_session.mount("http://", HTTPAdapter(max_retries=retries))
    _svix_service = session_scoped_container_getter.get("svix-backend")
    api_url = f"{_SVIX_SERVER_URL}/api/v1/health/"
    response = request_session.get(api_url)
    assert response

    # generate bearer token to authorize communication with the svix server
    exec = _svix_service.create_exec(f"svix-server jwt generate {_SVIX_ORG_ID}")
    exec_output = _svix_service.start_exec(exec["Id"])
    _svix_auth_token = exec_output.decode().replace("Token (Bearer): ", "")[:-1]

    return _svix_service


@pytest.fixture(autouse=True)
def svix_wiper():
    """Ensure stateless tests"""
    yield
    # wipe svix database after each test to ensure stateless tests
    exec = _svix_service.create_exec(
        f"svix-server wipe --yes-i-know-what-im-doing {_SVIX_ORG_ID}"
    )
    _svix_service.start_exec(exec["Id"])


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
def svix_server_url():
    return _SVIX_SERVER_URL


@pytest.fixture
def svix_auth_token():
    return _svix_auth_token


@pytest.fixture
def swh_webhooks(svix_server_url, svix_auth_token):
    from swh.webhooks.interface import Webhooks

    return Webhooks(svix_server_url=svix_server_url, svix_auth_token=svix_auth_token)
