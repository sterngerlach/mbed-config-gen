import click
import pathlib
import json
import subprocess
import copy
from typing import Optional
from . import consts


@click.group()
def cmd():
    pass


@cmd.command()
@click.argument(
    'out_dir',
    type=click.Path(
        file_okay=False, dir_okay=True,
        resolve_path=True, path_type=pathlib.Path))
@click.option(
    '--c-standard', type=click.Choice(['c17', 'c11', 'c99', '89']),
    default='c17', show_default=True,
    help='The version of C language standard for vscode intellisense.')
@click.option(
    '--cpp-standard', type=click.Choice(['c++20', 'c++17', 'c++14', 'c++11', 'c++03', 'c++98']),
    default='c++17', show_default=True,
    help='The version of C++ language standard for vscode intellisense.')
@click.option(
    '--compiler-path',
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False,
        resolve_path=True, path_type=pathlib.Path),
    help='Path to an arm compiler to use. '
    'If not set, the output of \"$ which arm-none-eabi-gcc\" is used.')
def generate(
        out_dir: pathlib.Path,
        c_standard: str,
        cpp_standard: str,
        compiler_path: Optional[pathlib.Path] = None):
    """Generate a template of your c_cpp_properties.json for quick start.

    Arguments:

    [OUR_DIR] The output directory where a template of your c_cpp_properties.json
    will be generated. If the specified directory doesn't exist,
    it'll be created including sub-directories involved.
    """
    click.echo(click.style('[GENERATE]', bold=True))

    # Check out_dir exists
    if not out_dir.exists():
        # If it doesn't, create out_dir including subdirectories
        out_dir.mkdir(parents=True)
        click.echo(
            f'-- Could not find the output directory ({out_dir}).\n'
            '   The directory was newly created including sub-directories.')
    click.echo(f'-- The output directory ({out_dir}) found.')

    # Find arm compiler path
    if compiler_path is None:
        ret = subprocess.run([
            'which',
            'arm-none-eabi-gcc'], capture_output=True)
        if ret.returncode != 0:
            err = ret.stderr.decode('utf-8')
            raise Exception(
                'Could not find arm-none-eabi-gcc in the search paths. '
                'Make sure that arm-none-eabi-gcc is installed in your machine. '
                'If not installed, try \"$ sudo apt install gcc-arm-none-eabi\".\n'
                f'Here\'s the error output from which command >>\n{err}')
        compiler_path = ret.stdout.decode('utf-8').strip()
        compiler_executable = compiler_path.split('/')[-1]
        click.echo(f'-- The default arm compiler (arm-none-eabi-gcc) found at <{compiler_path}>.')
    else:
        click.echo(f'-- The specified arm compiler ({compiler_executable}) found at <{compiler_path}>.')

    # Create c_cpp_properties.json
    vscode_conf = {
        'env': {},
        'configurations': [
            {
                'name': 'Mbed',
                'includePath': [],
                'defines': [],
                'compilerPath': str(compiler_path),
                'cStandard': c_standard,
                'cppStandard': cpp_standard,
                'intelliSenseMode': 'gcc-arm'
            }
        ],
        'version': 4}
    out_path = out_dir / consts.VSCODE_CONFFILE_NAME
    with (out_path).open('w') as file:
        json.dump(vscode_conf, file, indent=consts.VSCODE_CONFFILE_INDENT_LENGTH)
        click.echo(f'-- Saved your c_cpp_properties.json at <{out_path}>.')

    # Success
    click.echo('-- ' + click.style('SUCCEEDED', fg='green', bold=True))


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
         'If not specified, it\'s set to your current working directory.')
def configure(
        mbed_toolchain: str, mbed_target: str, vscode_conf_file: pathlib.Path,
        mbed_profile: str, mbed_program_dir: pathlib.Path) -> None:
    """Configure your build settings.

    Arguments:

    [MBED_TOOLCHAIN] The toolchain you are using to build your mbed application.
    Choose \'GCC_ARM\' or \'ARM\'.

    [MBED_TARGET] A build target for an mbed-enabled device (e.g. DISCO_L072CZ_LRWAN1).

    [VSCODE_CONF_FILE] Path to your c_cpp_properties.json.
    Create an \"Mbed\" entry in the file. The entry is inherited by
    \"MbedAuto\" entry which will be automatically generated by this tool.
    Use \"MbedAuto\" entry for your vscode intellisense.
    You can generate a template of your c_cpp_properties.json by \"$ mbed-vscode-tools generate\" command
    for quick start.
    """
    click.echo(click.style('[CONFIGURE]', bold=True))

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
    click.echo(f'-- Your c_cpp_properties.json ({vscode_conf_file}) found and loaded.')

    # Check validity of c_cpp_properties.json
    n = len(list(filter(  # The number of base entries (must be only one)
        lambda entry: entry['name'] == consts.VSCODE_CONFENTRY_BASE,
        vscode_conf['configurations'])))
    if n < 1:  # No base entries
        raise Exception(
            f'Could not find \"{consts.VSCODE_CONFENTRY_BASE}\" config entry in {vscode_conf_file}. '
            f'Create \"{consts.VSCODE_CONFENTRY_BASE}\" config entry.')
    elif n > 1:  # Duplication
        raise Exception(
            f'More than two \"{consts.VSCODE_CONFENTRY_BASE}\" config entries found in {vscode_conf_file}. '
            f'Leave one \"{consts.VSCODE_CONFENTRY_BASE}\" config entry and remove the others.')
    click.echo(f'-- No errros found in your c_cpp_properties.json')

    # Check if cmake build directory exists
    if not cmake_build_dir.exists():
        raise Exception(
            f'Could not find the cmake build directory ({cmake_build_dir}). '
            'Run \"$ mbed-tools configure\" first.')
    click.echo(f'-- The cmake build directory ({cmake_build_dir}) found.')

    # Check if cmake configuration file exists
    if not cmake_conf_file.exists():
        raise Exception(
            f'Could not find the cmake config file ({cmake_conf_file}). '
            'Run \"$ mbed-tools configure\" first.')
    click.echo(f'-- The cmake config file ({cmake_conf_file}) found.')

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
    click.echo(f'-- Succeeded to generate build.ninja.')

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
    click.echo(f'-- Saved your tool config file at <{tool_conf_file}>.')

    # Success
    click.echo('-- ' + click.style('SUCCEEDED', fg='green', bold=True))


@cmd.command()
@click.option(
    '--tool-conf-file',
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False,
        resolve_path=True, path_type=pathlib.Path),
    default=(pathlib.Path().cwd() / consts.TOOL_CONFFILE_NAME), show_default=True,
    help=f'Path to the tool config file ({consts.TOOL_CONFFILE_NAME}) generated by configure command. '
         f'If not specified, it\'s set to ./{consts.TOOL_CONFFILE_NAME}')
def update(tool_conf_file: pathlib.Path) -> None:
    """Update your c_cpp_properties.json

    Arguments: This sub-command has no positional arguments.
    """
    click.echo(click.style('[UPDATE]', bold=True))

    # Load tool config file
    if not tool_conf_file.exists():
        raise Exception(
            f'Could not find your tool config file at <{tool_conf_file}>.'
            'Set a correct path into \'--tool-conf-path\' option, or '
            'run \"$ mbed-vscode-tools configure\" if you haven\'t done yet.')
    with tool_conf_file.open('r') as file:
        tool_conf = json.load(file)
    click.echo(f'-- Your tool config file ({tool_conf_file}) found and loaded.')

    # Check if build.ninja exists
    cmake_build_dir = pathlib.Path(tool_conf['cmake_build_dir'])
    vscode_conf_file = pathlib.Path(tool_conf['vscode_conf_file'])
    ninja_build_file = pathlib.Path(tool_conf['ninja_build_file'])
    if not ninja_build_file.exists():
        raise Exception(
            f'Could not find build.ninja at <{ninja_build_file}>. '
            'Run \"$ mbed-vscode-tools configure\" first.')
    click.echo(f'-- Found build.ninja at <{ninja_build_file}>.')

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
    click.echo(f'-- Detected {len(includes)} include paths & {len(defines)} defines in your build.ninja.')

    # Load c_cpp_properties.json
    if not vscode_conf_file.exists():
        raise Exception(
            f'Could not find your c_cpp_properties.json at <{vscode_conf_file}>, '
            f'though the tool config file ({tool_conf_file}) points it. '
            'Run \"$ mbed-vscode-tools configure\" again to fix this problem.')
    with vscode_conf_file.open(mode='r') as file:
        vscode_conf = json.load(file)
    click.echo(f'-- Your c_cpp_properties ({vscode_conf_file}) found and loaded.')

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
    click.echo(f'-- Updated your c_cpp_properties.json.')

    # Success
    click.echo('-- ' + click.style('SUCCEEDED', fg='green', bold=True))


def main():
    cmd()


if __name__ == '__main__':
    main()
