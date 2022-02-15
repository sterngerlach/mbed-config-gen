import click
import pathlib
import json
import subprocess
import copy
from . import consts


@click.group()
def cmd():
    pass


@cmd.command()
@click.argument('mbed-toolchain', type=click.Choice(['GCC_ARM', 'ARM']))
@click.argument('mbed-target', type=str)
@click.argument(
    'vscode-conf-file',
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False,
        resolve_path=True, path_type=pathlib.Path))
@click.option(
    '--mbed-profile',
    type=click.Choice(['debug', 'develop', 'release']),
    default='develop', show_default=True,
    help='Choose an mbed build profile.')
@click.option(
    '--mbed-program-dir',
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True,
        resolve_path=True, path_type=pathlib.Path),
    default=pathlib.Path().cwd(), show_default=True,
    help='Path to an mbed program directory. '
         'If not specified, it\'s set to your working directory.')
def configure(
        mbed_toolchain: str, mbed_target: str, vscode_conf_file: pathlib.Path,
        mbed_profile: str, mbed_program_dir: pathlib.Path) -> None:
    """Configure build settings.

    [MBED_TOOLCHAIN] The toolchain you are using to build your mbed application.
    Choose \'GCC_ARM\' or \'ARM\'.

    [MBED_TARGET] A build target for an mbed-enabled device (e.g. DISCO_L072CZ_LRWAN1).

    [VSCODE_CONF_FILE] Path to your c_cpp_properties.json.
    Create an \"Mbed\" entry in the file. The entry is inherited by
    \"MbedGenerated\" entry which will be automatically generated by this tool.
    Use \"MbedGenerated\" entry for your vscode intellisense.
    """

    click.echo('[Configure]')
    cmake_build_dir = \
        mbed_program_dir / \
        consts.CMAKE_ROOTDIR_NAME / \
        mbed_target / \
        mbed_profile / \
        mbed_toolchain
    cmake_conf_file = cmake_build_dir / consts.CMAKE_CONFFILE_NAME

    # Load c_cpp_properties.json
    with vscode_conf_file.open(mode='r') as file:
        vscode_conf = json.load(file)

    # Check validity of c_cpp_properties.json
    n = len(list(filter(  # The number of base entries (must be only one)
        lambda entry: entry['name'] == consts.VSCODE_CONFENTRY_BASE,
        vscode_conf['configurations'])))
    if n < 1:  # No base entries
        raise Exception(
            f'Could not find \"{consts.VSCODE_CONFENTRY_BASE}\" entry in {vscode_conf_file}. '
            f'Create \"{consts.VSCODE_CONFENTRY_BASE}\" entry.')
    elif n > 1:  # Duplication
        raise Exception(
            f'More than two \"{consts.VSCODE_CONFENTRY_BASE}\" entries found in {vscode_conf_file}. '
            f'Leave one \"{consts.VSCODE_CONFENTRY_BASE}\" entry and remove the others.')
    click.echo('---- c_cpp_properties.json validation done.')

    # Check if cmake build directory exists
    if not cmake_build_dir.exists():
        raise Exception(
            f'Could not find the cmake build directory ({cmake_build_dir}). '
            'Run \'$ mbed-tools configure\' first.')
    click.echo(f'---- CMake build directory ({cmake_build_dir}) found.')

    # Check if cmake configuration file exists
    if not cmake_conf_file.exists():
        raise Exception(
            f'Could not find the cmake config file ({cmake_conf_file}). '
            'Run \'$ mbed-tools configure\' first.')
    click.echo(f'---- CMake config file ({cmake_conf_file}) found.')

    # Generate build.ninja
    ret = subprocess.run([
        'cmake',
        '-S', str(mbed_program_dir),
        '-B', str(cmake_build_dir),
        '-GNinja'], capture_output=True)
    if ret.returncode != 0:
        err = ret.stderr.decode('utf-8')
        raise Exception(
            'Failed to generate build.ninja for some reasons. '
            f'Here\'s the error output from cmake >>\n{err}')
    click.echo('---- build.ninja generation done.')

    # Save config json file
    tool_conf_file = mbed_program_dir / consts.TOOL_CONFFILE_NAME
    conf = {
        'mbed_toolchain': mbed_toolchain,
        'mbed_target': mbed_target,
        'mbed_profile': mbed_profile,
        'mbed_program_dir': str(mbed_program_dir),
        'cmake_build_dir': str(cmake_build_dir),
        'cmake_conf_file': str(cmake_conf_file),
        'vscode_conf_file': str(vscode_conf_file),
        'ninja_build_file': str(cmake_build_dir / consts.NINJA_BUILDFILE_NAME)}
    with tool_conf_file.open('w') as file:
        json.dump(conf, file, indent=consts.TOOL_CONFFILE_INDENT_LENGTH)
    click.echo(f'---- Tool config file was saved at <{tool_conf_file}>.')


@cmd.command()
@click.option(
    '--tool-conf-file',
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False,
        resolve_path=True, path_type=pathlib.Path),
    default=(pathlib.Path().cwd() / consts.TOOL_CONFFILE_NAME), show_default=True,
    help=f'Path to the tool configuration file ({consts.TOOL_CONFFILE_NAME}) generated by configure command. '
         f'If not specified, it\'s set to ./{consts.TOOL_CONFFILE_NAME}')
def update(tool_conf_file: pathlib.Path) -> None:
    """Update your c_cpp_properties.json
    """

    click.echo('[Update]')
    # Check if tool configuration file exists
    if not tool_conf_file.exists():
        raise Exception(
            f'Could not find your tool configuration file at <{tool_conf_file}>.'
            'Set a correct path into \'--tool-conf-path\' option, or '
            'run \'$ mbed-vscode-tools configure\' if you haven\'t done yet.')
    click.echo('---- Tool configuration file found.')

    # Load tool configuration file
    with tool_conf_file.open('r') as file:
        tool_conf = json.load(file)
    vscode_conf_file = pathlib.Path(tool_conf['vscode_conf_file'])
    cmake_build_dir = pathlib.Path(tool_conf['cmake_build_dir'])

    # Check if build.ninja exists
    ninja_build_file = pathlib.Path(tool_conf['ninja_build_file'])
    if not ninja_build_file.exists():
        raise Exception(
            f'Could not find build.ninja at <{ninja_build_file}>. '
            'Run \'$ mbed-vscode-tools configure\' first.')
    click.echo('---- build.ninja found.')

    # Parse build.ninja
    defines, includes = [], []
    with ninja_build_file.open(mode='r') as file:
        lines = file.readlines()
        defines_done = False
        includes_done = False
        for line in lines:
            line = line.strip()

            # Parse defines
            if not defines_done and line.startswith('DEFINES = '):
                for define in line.split('-D')[1:]:  # Remove 'DEFINES = '
                    define = define.strip()
                    if define not in defines:
                        defines.append(define)
                defines_done = True

            # Parse includes
            if not includes_done and line.startswith('INCLUDES = '):
                for include in line.split('-I')[1:]:  # Remove 'INCLUDES = '
                    include = include.strip()[1:-1]  # Remove "" both side
                    if include not in includes:
                        includes.append(include)
                includes_done = True

            # Termination
            if defines_done and includes_done:
                break
    # Manually add one include
    # TODO: Should parse this automatically as well
    includes.append(str(cmake_build_dir / '_deps' / 'greentea-client-src' / 'include'))

    # Show build.ninja parse result
    click.echo(f'---- {len(defines)} defines & {len(includes)} include paths were extracted from <{ninja_build_file}>.')

    # Load c_cpp_properties.json
    if not vscode_conf_file.exists():
        raise Exception(
            f'Could not find your c_cpp_properties.json at <{vscode_conf_file}>, '
            f'though the tool configuration file ({tool_conf_file}) points the path. '
            'Run \'$ mbed-vscode-tools configure\' again to fix the problem.')
    with vscode_conf_file.open(mode='r') as file:
        vscode_conf = json.load(file)

    # Get base entry
    base_entry = next(filter(
        lambda entry: entry['name'] == consts.VSCODE_CONFENTRY_BASE,
        vscode_conf['configurations']))

    # Create new auto entry
    auto_entry = copy.deepcopy(base_entry)
    auto_entry['name'] = consts.VSCODE_CONFENTRY_AUTO

    # Update includes
    if 'includePath' not in auto_entry:
        auto_entry['includePath'] = []
    auto_entry['includePath'].extend(includes)

    # Update defines
    if 'defines' not in auto_entry:
        auto_entry['defines'] = []
    auto_entry['defines'].extend(defines)

    # Save c_cpp_properties.json
    new_entries = list(filter(
        lambda entry: entry['name'] != consts.VSCODE_CONFENTRY_AUTO,
        vscode_conf['configurations']))
    new_entries.append(auto_entry)
    vscode_conf['configurations'] = new_entries
    with vscode_conf_file.open('w') as file:
        json.dump(vscode_conf, file, indent=consts.VSCODE_CONFFILE_INDENT_LENGTH)
    click.echo(f'---- Your c_cpp_properties ({vscode_conf_file}) updated.')


def main():
    cmd()


if __name__ == '__main__':
    main()
