# This is not an executable script.

from __future__ import print_function
from __future__ import unicode_literals

#print("consoletools: on_import")
import sys

# ------------------------------------------------------------------------
# Tools & utilities
# ------------------------------------------------------------------------

# noinspection PyBroadException
def prompt(prompt, validate):
    """Prompt the user for the answer to a question.
    :param prompt: The prompt to display.
    :param validate: The validation lambda to run.
    """
    while True:  # Wait for the user to answer
        try:  # When we get an answer, test it
            result = validate(raw_input(prompt))
            if result:  # Yay, it was the answer we sought.
                return result
        except (KeyboardInterrupt, EOFError):
            sys.exit("\nAborted")  # This is not my cookie, sir.
        except:  # Yes, it's too broad, but so is my van.
            pass  # to the right.


# Define a quick inline function to respond to both long and short yes/no.
def select_yes_no(selection):
    selection = selection.lower()
    if selection in ('y', 'yes'):
        return 'y'
    elif selection in ('n', 'no'):
        return 'n'


def calc_bar(progress, length):
    """Calculate a progress bar of task completion
    :param progress: Percentage of progress.
    :param length: Total length of bar.
    """
    fill = int((progress / 100.0) * length)
    return '=' * fill + ' ' * (length - fill)


def calc_finish(read_bytes, total_bytes, elapsed):
    """Calculate estimated time remaining until task completion
    :param read_bytes: Number of bytes read since the operation was begun.
    :param total_bytes: Number of bytes total before the operation is complete.
    :param elapsed: Number of seconds elapsed.
    """
    if read_bytes < 1:  # We haven't done anything yet!
        return 0  # Don't return something weird like None, just plain old zero.
    return long(((total_bytes - read_bytes) * elapsed) / read_bytes)


#print("consoletools: done_import")

# ------------------------------------------------------------------------
# Main program
# ------------------------------------------------------------------------

# If we're invoked as a program; instead of imported as a class...
if __name__ == '__main__':
    print("This class is supposed to be imported, not executed.")