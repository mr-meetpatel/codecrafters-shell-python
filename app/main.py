import sys
import os
import subprocess
import shlex
import readline
from abc import ABC, abstractmethod

def find_executable(command_name):
    """Search for an executable in the system PATH."""
    paths = os.getenv("PATH", "").split(":")
    for path in paths:
        full_path = os.path.join(path, command_name)
        if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
            return full_path
    return None


def get_executables_in_path():
    """Retrieve all executable files from directories listed in PATH."""
    executables = set()
    paths = os.getenv("PATH", "").split(":")
    for path in paths:
        if os.path.isdir(path):
            try:
                for file in os.listdir(path):
                    full_path = os.path.join(path, file)
                    if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                        executables.add(file)
            except PermissionError:
                continue  # Ignore directories we can't access
    return sorted(executables)

class CommandCompleter:
    def __init__(self):
        self.matches = []
        self.last_text = ""
        self.match_index = -1
        self.tab_count = 0  # Track number of times TAB is pressed

    def find_executables(self):
        """Retrieve all executables in the PATH."""
        executables = set()
        for path in os.getenv("PATH", "").split(":"):
            if os.path.isdir(path):
                try:
                    executables.update(
                        f for f in os.listdir(path) if os.access(os.path.join(path, f), os.X_OK)
                    )
                except PermissionError:
                    continue
        return sorted(executables)

    def longest_common_prefix(self, words):
        """Find the longest common prefix of a list of words."""
        if not words:
            return ""
        prefix = words[0]
        for word in words[1:]:
            while not word.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        return prefix

    def completer(self, text, state):
        """Handles tab completion with progressive prefix matching."""
        builtins = ["echo", "exit", "type"]
        external_cmds = self.find_executables()  # Get commands from PATH
        all_commands = sorted(set(builtins + list(external_cmds)))

        if state == 0:  # First TAB press
            if text != self.last_text:
                self.matches = [cmd for cmd in all_commands if cmd.startswith(text)]
                self.match_index = -1
                self.last_text = text
                self.tab_count = 0  # Reset tab counter

            if len(self.matches) == 1:
                return self.matches[0] + " "  # Auto-complete if there's only one match
            elif len(self.matches) > 1:
                common_prefix = self.longest_common_prefix(self.matches)
                if common_prefix != text:
                    return common_prefix  # Complete up to the longest common prefix
                else:
                    self.tab_count += 1
                    if self.tab_count == 1:
                        print("\a", end="", flush=True)  # Bell sound
                        return None  # Do nothing on first TAB
                    elif self.tab_count == 2:
                        print("\n" + "  ".join(self.matches))  # Show suggestions
                        print(f"$ {text}", end="", flush=True)  # Keep input unchanged
                        return None  # Don't modify input
                    else:  # Cycle through options
                        self.match_index = (self.match_index + 1) % len(self.matches)
                        return self.matches[self.match_index] + " "

        return None  # No matches

completer = CommandCompleter()

# Register the completer
readline.set_completer(completer.completer)
readline.parse_and_bind("tab: complete")


# Command Interface
class Command(ABC):
    @abstractmethod
    def execute(self, args, stdout=sys.stdout, stderr=sys.stderr):
        pass


# Built-in Commands
class EchoCommand(Command):
    def execute(self, args, stdout=sys.stdout, stderr=sys.stderr):
        print(" ".join(args), file=stdout)


class ExitCommand(Command):
    def execute(self, args, stdout=sys.stdout, stderr=sys.stderr):
        if len(args) == 1 and args[0].isdigit():
            sys.exit(int(args[0]))
        sys.exit(0)


class TypeCommand(Command):
    def __init__(self, registry):
        self.registry = registry

    def execute(self, args, stdout=sys.stdout, stderr=sys.stderr):
        if not args:
            print("type: missing argument", file=stderr)
            return

        command_name = args[0]

        if command_name in self.registry.commands:
            print(f"{command_name} is a shell builtin", file=stdout)
            return

        executable_path = find_executable(command_name)
        if executable_path:
            print(f"{command_name} is {executable_path}", file=stdout)
        else:
            print(f"{command_name}: not found", file=stderr)


# Command Registry
class CommandRegistry:
    def __init__(self):
        self.commands = {}

    def register(self, name, command):
        self.commands[name] = command

    def execute(self, command_input):
        """Process command input, detect redirections, and execute the command."""
        parts = shlex.split(command_input)

        stdout_target = sys.stdout
        stderr_target = sys.stderr

        command_parts = parts  # Initial command parts before redirection handling

        # Handle stdout append redirection (>>, 1>>)
        if ">>" in parts or "1>>" in parts:
            try:
                operator_index = parts.index(">>") if ">>" in parts else parts.index("1>>")
                command_parts = parts[:operator_index]
                output_file = parts[operator_index + 1]
                stdout_target = open(output_file, "a")  # Append mode

            except (IndexError, IOError) as e:
                print(f"Error handling stdout append redirection: {e}", file=sys.stderr)
                return

        # Handle stdout overwrite redirection (>, 1>)
        elif ">" in parts or "1>" in parts:
            try:
                operator_index = parts.index(">") if ">" in parts else parts.index("1>")
                command_parts = parts[:operator_index]
                output_file = parts[operator_index + 1]
                stdout_target = open(output_file, "w")  # Overwrite mode

            except (IndexError, IOError) as e:
                print(f"Error handling stdout redirection: {e}", file=sys.stderr)
                return

        # Handle stderr append redirection (2>>)
        if "2>>" in parts:
            try:
                operator_index = parts.index("2>>")
                command_parts = command_parts[:operator_index]
                error_file = parts[operator_index + 1]
                stderr_target = open(error_file, "a")  # Append mode

            except (IndexError, IOError) as e:
                print(f"Error handling stderr append redirection: {e}", file=sys.stderr)
                return

        # Handle stderr overwrite redirection (2>)
        elif "2>" in parts:
            try:
                operator_index = parts.index("2>")
                command_parts = command_parts[:operator_index]
                error_file = parts[operator_index + 1]
                stderr_target = open(error_file, "w")

            except (IndexError, IOError) as e:
                print(f"Error handling stderr redirection: {e}", file=sys.stderr)
                return

        # Execute command with redirections
        self._execute_command(command_parts, stdout=stdout_target, stderr=stderr_target)

        # Close files if redirected
        if stdout_target is not sys.stdout:
            stdout_target.close()
        if stderr_target is not sys.stderr:
            stderr_target.close()

    def _execute_command(self, parts, stdout=sys.stdout, stderr=sys.stderr):
        """Execute a command with optional stdout and stderr redirection."""
        if not parts:
            return

        command_name = parts[0]
        args = parts[1:]

        if command_name in self.commands:
            self.commands[command_name].execute(args, stdout=stdout, stderr=stderr)
        else:
            self.run_external_command(command_name, args, stdout=stdout, stderr=stderr)

    def run_external_command(self, name, args, stdout=sys.stdout, stderr=sys.stderr):
        executable_path = find_executable(name)
        if executable_path:
            try:
                subprocess.run([name] + args, stdout=stdout, stderr=stderr)
            except Exception as e:
                print(f"Error running {name}: {e}", file=sys.stderr)
        else:
            print(f"{name}: command not found", file=stderr)

class PwdCommand(Command):

    def execute(self, args, stdout=sys.stdout, stderr=sys.stderr):
        """Prints the absolute path of the current working directory."""
        print(os.getcwd(), file=stdout)


class CdCommand(Command):
    def execute(self, args, stdout=sys.stdout, stderr=sys.stderr):
        """Changes the current working directory."""
        if not args or len(args) != 1:
            print("cd: missing operand", file=stderr)
            return

        target_directory = args[0]

        # Handle `~` as the home directory
        if target_directory == "~":
            target_directory = os.getenv("HOME", "/")

        # Check if the directory exists and is accessible
        if os.path.isdir(target_directory):
            try:
                os.chdir(target_directory)
            except PermissionError:
                print(f"cd: {target_directory}: Permission denied", file=stderr)
        else:
            print(f"cd: {target_directory}: No such file or directory", file=stderr)


# Main Shell Loop
def main():
    registry = CommandRegistry()
    registry.register("echo", EchoCommand())
    registry.register("exit", ExitCommand())
    registry.register("type", TypeCommand(registry))
    registry.register("pwd", PwdCommand())
    registry.register("cd", CdCommand())

    while True:
        try:
            command_input = input("$ ")
            registry.execute(command_input)
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()