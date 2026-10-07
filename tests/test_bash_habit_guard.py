"""Shell habits are recognized at executable and redirection token boundaries."""

import pytest

from cloudra.tools.core.bash_habit_guard import bash_file_write_warning, is_substantive_bash_command


@pytest.mark.parametrize("command", [
    "printf x>out.txt", "cat input|tee out.txt", "echo x >12345",
    "cd /tmp; echo x>out.txt", "true && /usr/bin/sed -i.bak s/a/b/ f",
    "env sed -i s/a/b/ f", ">out.txt", "2>>out.txt", "echo x&>out.txt",
    "cat > out.txt <<'EOF'\nunmatched ' quote in data\nEOF",
])
def test_workspace_content_write_is_detected(command):
    assert bash_file_write_warning(command) is not None
    assert is_substantive_bash_command({"command": command})


@pytest.mark.parametrize("command", [
    "echo 'tee out.txt'", "echo sed -i x f", "echo '<<EOF > out.txt'",
    "printf '%s' '>'", "grep '>' input", "python script.py >out.log",
    "echo x 2>&1", "echo x > /dev/null", "cat input | tee /dev/null",
    "sed -n '1,5p' f", "awk 'BEGIN {print 1}'", "cat <<EOF\nsed -i x f\nEOF",
])
def test_literals_and_output_capture_do_not_warn(command):
    assert bash_file_write_warning(command) is None


@pytest.mark.parametrize("command", [
    "cd /tmp && orca input.inp", "env OMP_NUM_THREADS=2 /opt/orca/orca input.inp",
    "env 'OMP_NUM_THREADS=2' orca input.inp", 'env "OMP_NUM_THREADS=2" /opt/orca/orca input.inp',
    "env -- OMP_NUM_THREADS=2 orca input.inp", "IFS= env 'OMP_NUM_THREADS=2' orca input.inp",
    "true; xtb input.xyz", "cat input|g16", "orca input.inp &",
])
def test_compute_command_in_execution_segment_is_substantive(command):
    assert is_substantive_bash_command({"command": command})


@pytest.mark.parametrize("command", ["echo orca", "echo 'orca input.inp'", "cat orca.log"])
def test_compute_program_as_argument_is_not_substantive(command):
    assert not is_substantive_bash_command({"command": command})


@pytest.mark.parametrize("command", [
    "echo 'unclosed", "echo >", "cat input |", "echo $(id",
    "env --split-string='orca input.inp'", "env --made-up=value",
])
def test_malformed_commands_do_not_fall_back_to_guessing(command):
    with pytest.raises(ValueError, match="Invalid shell command"):
        bash_file_write_warning(command)
    with pytest.raises(ValueError, match="Invalid shell command"):
        is_substantive_bash_command({"command": command})
