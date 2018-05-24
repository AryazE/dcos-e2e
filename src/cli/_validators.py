"""
Validators for CLI options.
"""

import re
import subprocess
import uuid
from pathlib import Path
from shutil import rmtree
from tempfile import gettempdir
from typing import Any, Dict, List, Optional, Tuple, Union

import click
import click_spinner
import docker
import yaml

from dcos_e2e.node import Node

from ._common import (
    ClusterContainers,
    ContainerInspectView,
    existing_cluster_ids,
)
from ._utils import is_enterprise


def validate_dcos_configuration(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Union[int, bool, str],
) -> Dict[str, Any]:
    """
    Validate that a given value is a file containing a YAML map.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    if value is None:
        return {}

    content = Path(str(value)).read_text()

    try:
        return dict(yaml.load(content) or {})
    except ValueError:
        message = '"{content}" is not a valid DC/OS configuration'.format(
            content=content,
        )
    except yaml.YAMLError:
        message = '"{content}" is not valid YAML'.format(content=content)

    raise click.BadParameter(message=message)


def validate_cluster_id(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Optional[Union[int, bool, str]],
) -> str:
    """
    Validate that a given value is a YAML map.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    if value in existing_cluster_ids():
        message = 'A cluster with the id "{value}" already exists'.format(
            value=value,
        )
        raise click.BadParameter(message=message)

    # This matches the Docker ID regular expression.
    # This regular expression can be seen by running:
    # > docker run -it --rm --id=' WHAT ? I DUNNO ! ' alpine
    if not re.fullmatch('^[a-zA-Z0-9][a-zA-Z0-9_.-]*$', str(value)):
        message = (
            'Invalid cluster id "{value}", only [a-zA-Z0-9][a-zA-Z0-9_.-] '
            'are allowed and the cluster ID cannot be empty.'
        ).format(value=value)
        raise click.BadParameter(message)

    return str(value)


def validate_cluster_exists(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Optional[Union[int, bool, str]],
) -> str:
    """
    Validate that a cluster exists with the given name.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    if value is None:
        if 'default' in existing_cluster_ids():
            return 'default'
        message = '--cluster-id was not given and no cluster "default" exists'
        raise click.BadParameter(message)

    cluster_id = str(value)
    if cluster_id not in existing_cluster_ids():
        message = 'Cluster "{value}" does not exist'.format(value=value)
        raise click.BadParameter(message)

    return cluster_id


def validate_path_is_directory(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Optional[Union[int, bool, str]],
) -> Optional[Path]:
    """
    Validate that a path is a directory.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    if value is None:
        return None

    path = Path(str(value))
    if not path.is_dir():
        message = '"{path}" is not a directory.'.format(path=str(path))
        raise click.BadParameter(message=message)

    return path


def validate_path_pair(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Any,
) -> List[Tuple[Path, Path]]:
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    result = []  # type: List[Tuple[Path, Path]]

    if value is None:
        return result

    for path_pair in value:
        try:
            [local_path, remote_path] = list(map(Path, path_pair.split(':')))
        except ValueError:
            message = (
                '"{path_pair}" is not in the format '
                '/absolute/local/path:/remote/path.'
            ).format(path_pair=path_pair)
            raise click.BadParameter(message=message)

        if not local_path.exists():
            message = '"{local_path}" does not exist.'.format(
                local_path=local_path,
            )
            raise click.BadParameter(message=message)

        if not remote_path.is_absolute():
            message = '"{remote_path} is not an absolute path.'.format(
                remote_path=remote_path,
            )
            raise click.BadParameter(message=message)

        result.append((local_path, remote_path))

    return result


def validate_volumes(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Any,
) -> List[docker.types.Mount]:
    """
    Turn volume definition strings into ``Mount``s that ``docker-py`` can use.
    """
    for _ in (ctx, param):
        pass
    mounts = []
    for volume_definition in value:
        parts = volume_definition.split(':')

        if len(parts) == 1:
            host_src = None
            [container_dst] = parts
            read_only = False
        elif len(parts) == 2:
            host_src, container_dst = parts
            read_only = False
        elif len(parts) == 3:
            host_src, container_dst, mode = parts
            if mode == 'ro':
                read_only = True
            elif mode == 'rw':
                read_only = False
            else:
                message = (
                    'Mode in "{volume_definition}" is "{mode}". '
                    'If given, the mode must be one of "ro", "rw".'
                ).format(
                    volume_definition=volume_definition,
                    mode=mode,
                )
                raise click.BadParameter(message=message)
        else:
            message = (
                '"{volume_definition}" is not a valid volume definition. '
                'See '
                'https://docs.docker.com/engine/reference/run/#volume-shared-filesystems '  # noqa: E501
                'for the syntax to use.'
            ).format(volume_definition=volume_definition)
            raise click.BadParameter(message=message)

        mount = docker.types.Mount(
            source=host_src,
            target=container_dst,
            type='bind',
            read_only=read_only,
        )
        mounts.append(mount)
    return mounts


def validate_ovpn_file_does_not_exist(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Any,
) -> Path:
    """
    If the given file path exists already, show an error message explaining how
    to use the file as an OpenVPN configuration.
    """
    force = bool('force' in ctx.params)
    path = Path(value).expanduser()
    if path.is_dir():
        path = path / 'docker-for-mac.ovpn'

    if path.suffix != '.ovpn':
        message = '"{value}" does not have the suffix ".ovpn".'.format(
            value=value,
        )
        raise click.BadParameter(message=message)

    for _ in (ctx, param):
        pass

    profile_name = path.name[:-len('.ovpn')]

    message = (
        '"{value}" already exists so no new OpenVPN configuration was '
        'created.'
        '\n'
        '\n'
        'To use {value}:'
        '\n'
        '1. Install an OpenVPN client such as Tunnelblick '
        '(https://tunnelblick.net/downloads.html) '
        'or Shimo (https://www.shimovpn.com).'
        '\n'
        '2. Run "open {value}".'
        '\n'
        '3. In your OpenVPN client, connect to the new "{profile_name}" '
        'profile.'
        '\n'
        '4. Run "dcos-docker doctor" to confirm that everything is working.'
    ).format(
        value=value,
        profile_name=profile_name,
    )

    if path.exists() and not force:
        raise click.BadParameter(message=message)

    return path


def validate_node_reference(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Any,
) -> Node:
    """
    Get a node from a "reference" which is one of:

        * A node's IP address
        * A node's Docker container
        * A reference in the format "<role>_<number>"

    Error if there is no such node for the cluster with a given ``cluster_id``.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (param, ):
        pass

    cluster_id = ctx.params['cluster_id']
    cluster_containers = ClusterContainers(cluster_id=cluster_id)

    containers = {
        *cluster_containers.masters,
        *cluster_containers.agents,
        *cluster_containers.public_agents,
    }

    for container in containers:
        inspect_data = ContainerInspectView(container=container).to_dict()
        reference = inspect_data['e2e_reference']
        ip_address = inspect_data['ip_address']
        container_name = inspect_data['docker_container_name']
        container_id = inspect_data['docker_container_id']
        accepted = (
            reference,
            reference.upper(),
            ip_address,
            container_name,
            container_id,
        )
        if value in accepted:
            return cluster_containers.to_node(container=container)

    message = (
        'No such node in cluster "{cluster_id}" with IP address, Docker '
        'container ID or node reference "{value}". '
        'Node references can be seen with ``dcos_docker inspect``.'
    ).format(
        cluster_id=cluster_id,
        value=value,
    )
    raise click.BadParameter(message=message)


def validate_variant(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Any,
) -> str:
    """
    Return whether to attempt to create a cluster with the given artifact as
    "enterprise" or "oss".
    """
    # We "use" variables to satisfy linting tools.
    for _ in (param, ):
        pass

    if value != 'auto':
        return str(value)

    artifact_path = Path(ctx.params['artifact']).resolve()
    doctor_message = 'Try `dcos-docker doctor` for troubleshooting help.'
    base_workspace_dir = ctx.params['workspace_dir'] or Path(gettempdir())
    workspace_dir = base_workspace_dir / uuid.uuid4().hex
    workspace_dir.mkdir()

    try:
        with click_spinner.spinner():
            enterprise = is_enterprise(
                build_artifact=artifact_path,
                workspace_dir=workspace_dir,
            )
    except subprocess.CalledProcessError as exc:
        rmtree(path=str(workspace_dir), ignore_errors=True)
        click.echo(doctor_message)
        click.echo()
        click.echo('Original error:')
        click.echo(exc.stderr)
        raise

    rmtree(path=str(workspace_dir), ignore_errors=True)
    return 'enterprise' if enterprise else 'oss'


def validate_environment_variable(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Any,
) -> Dict[str, str]:
    """
    Validate that environment variables are set as expected.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (param, ctx):
        pass

    env = {}
    for definition in value:
        try:
            key, val = definition.split(sep='=', maxsplit=1)
        except ValueError:
            message = (
                '"{definition}" does not match the format "<KEY>=<VALUE>".'
            ).format(definition=definition)
            raise click.BadParameter(message=message)
        env[key] = val
    return env
