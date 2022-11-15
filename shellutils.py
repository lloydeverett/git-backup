import os
import plumbum
from plumbum import FG, BG
from plumbum import local

def touch(path):
    plumbum.cmd.touch(path)

def listdir_nohidden(path):
    for f in os.listdir(path):
        if not f.startswith('.'):
            yield f

def try_input(prompt):
    try:
        return input(prompt)
    except KeyboardInterrupt:
        return None

def input_yes_no(prompt):
    response = try_input(prompt)
    if response is None:
        return None
    if response.upper() == 'Y' or response.upper() == 'YES':
        return True
    elif response.upper() == 'N' or response.upper() == 'NO':
        return False
    else:
        return None

