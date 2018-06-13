"""
Helpers for building Docker images.
"""

import inspect
import os
from pathlib import Path

import docker

from dcos_e2e.distributions import Distribution
from dcos_e2e.docker_versions import DockerVersion


def _base_dockerfile(linux_distribution: Distribution) -> Path:
    """
    Return the directory including a Dockerfile to use for the base OS image.
    """
    dcos_docker_distros = {
        Distribution.CENTOS_7: 'centos-7',
        Distribution.COREOS: 'coreos',
    }

    distro_path_segment = dcos_docker_distros[linux_distribution]
    current_file = inspect.stack()[0][1]
    current_parent = Path(os.path.abspath(current_file)).parent
    dockerfiles = current_parent / 'resources' / 'dockerfiles' / 'base'
    return dockerfiles / distro_path_segment


def _docker_dockerfile() -> Path:
    """
    Return the directory including a Dockerfile to use to install Docker.
    """
    current_file = inspect.stack()[0][1]
    current_parent = Path(os.path.abspath(current_file)).parent
    return current_parent / 'resources' / 'dockerfiles' / 'base-docker'


def build_docker_image(
    tag: str,
    linux_distribution: Distribution,
    docker_version: DockerVersion,
) -> None:
    """
    Build a Docker image to use for node containers.
    """
    base_tag = tag + ':base'

    client = docker.from_env(version='auto')
    base_dockerfile = _base_dockerfile(linux_distribution=linux_distribution)
    docker_dockerfile = _docker_dockerfile()

    docker_versions = {
        DockerVersion.v1_11_2: '1.11.2',
        DockerVersion.v1_13_1: '1.13.1',
        DockerVersion.v17_12_1_ce: '17.12.1-ce',
    }

    client.images.build(
        path=str(base_dockerfile),
        rm=True,
        forcerm=True,
        tag=base_tag,
    )

    client.images.build(
        path=str(docker_dockerfile),
        rm=True,
        forcerm=True,
        tag=tag,
        buildargs={'DOCKER_VERSION': docker_versions[docker_version]},
    )
