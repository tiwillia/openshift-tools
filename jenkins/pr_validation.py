#!/usr/bin/env python

import requests
import sys
import subprocess
import os
import pprint
import yaml_validation
import re
from pylint import epylint as lint

GITHUB_API_URL = "https://api.github.com/"
REPO = "tiwillia/openshift-tools"
PULL_ID_ENVVAR = "TOOLS_PULL_ID"
PROD_BRANCH_NAME = "prod"
PYLINT_RCFILE = "/root/openshift-tools/jenkins/.pylintrc"
LINT_EXCLUDE_FILE_LIST = [
'prometheus_client'
'ansible/inventory/aws/hosts/ec2.py'
'ansible/inventory/gce/hosts/gce.py'
'docs/*']

Errors = []

# Mostly stolen from parent.py
# Run cli command and exit if an error occurs
def run_cli_cmd(cmd, in_stdout=None, in_stderr=None, exit_on_fail=True):
    '''Run a command and return its output'''
    if not in_stderr:
        proc = subprocess.Popen(cmd, bufsize=-1, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=False)
    else:
        proc = subprocess.check_output(cmd, bufsize=-1, stdout=in_stdout, stderr=in_stderr, shell=False)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        if exit_on_fail:
            print("Unable to run " + " ".join(cmd) + " due to error: " + stderr)
            sys.exit(proc.returncode)
        else:
            return False, stdout
    else:
        return True, stdout

def linter(base_sha, remote_sha):
    print("Running pylint")
    _, diff_output = run_cli_cmd(["/usr/bin/git", "diff", "--name-only", base_sha, remote_sha, "--diff-filter=ACM"])
    diff_file_list = diff_output.split(' ')
    file_list = []
       
    # For each file in the diff, confirm it should be linted 
    for dfile in diff_file_list:
        # Skip linting for specific files
        if dfile in LINT_EXCLUDE_FILE_LIST:
            continue
        # Skip linting if dfile is a directory or other non-file type
        if not os.path.isfile(dfile):
            continue
        # Skip linting if the file is documentation
        _, ext = os.path.splitext(dfile)
        if ext == "adoc" or ext == "asciidoc":
            continue
        # Finally, if this file is indeed a python script, add it to the list to be linted
        file_type = run_cli_cmd(["/usr/bin/file", "-b", dfile])
        if re.I.match(r'python', file_type):
            file_list.append(dfile)
                
    pylint_options = "--rcfile=" + PYLINT_RCFILE + " " + " ".join(file_list)
    print(pylint_options)
    stdout, stderr = lint.py_run(pylint_options, return_std=True)
    if len(stderr.read()) > 0:
        for err in stderr.read().split('\n'):
            Errors.append("Pylint: " + err)
        return
    print(stdout.read())

def validate_yaml(base_sha, remote_sha):
    print("Validating yaml")
    sys.argv = [sys.argv[0], base_sha, remote_sha, ""]
    # TODO Need to build getting this file into the image: https://raw.githubusercontent.com/openshift/openshift-ansible/master/git/yaml_validation.py
    # We'll no longer need yaml_validation.sh afterwards

    # This is a bit ugly, it will exit if an error is found, which doesn't give us much of an oppurtunity to handle errors completely in the script
    yaml_validation.main() 

def ensure_stg_contains(commit_id):
    print("Ensuring stage branch also contains " + commit_id)
    # git co stg
    run_cli_cmd(['/usr/bin/git', 'checkout', 'stg'])
    # git pull latest
    run_cli_cmd(['/usr/bin/git', 'pull'])
    # setup on the <prod> branch in git
    run_cli_cmd(['/usr/bin/git', 'checkout', 'prod'])
    run_cli_cmd(['/usr/bin/git', 'pull'])
    # merge the passed in commit into my current <branch>
    run_cli_cmd(['/usr/bin/git', 'merge', commit_id])

    commits_not_in_stg = []

    # get the differences from stg and <branch>
    _, rev_list = run_cli_cmd(['/usr/bin/git', 'rev-list', '--left-right', 'stg...prod'])
    for commit in rev_list.split('\n'):
        # continue if it is already in stg
        if not commit or commit.startswith('<'):
            continue
        # remove the first char '>'
        commit = commit[1:]
        ok, branches = run_cli_cmd(['/usr/bin/git', 'branch', '-q', '-r', '--contains', commit], in_stderr=None, exit_on_fail=False)
        if ok and len(branches) == 0:
            continue
        if 'origin/stg/' not in branches:
            commits_not_in_stg.append(commit)

    if len(commits_not_in_stg) > 0:
        Errors.append("These commits are not in stage:\n\t" + " ".join(commits_not_in_stg))

def main():
    # Get the pull ID from environment variable
    pull_id = os.getenv(PULL_ID_ENVVAR, "")
    if pull_id == "":
            # Exit with an error if no pull ID could be found
            print("ERROR: " + PULL_ID_ENVVAR + "is not defined in env")
            sys.exit(1)

    pull_url = GITHUB_API_URL + "repos/" + REPO + "/pulls/" + pull_id
    # Attempt to get the pull request
    response = requests.get(pull_url)
    # Raise an error if we get a non-2XX status code back
    response.raise_for_status()

    pull_content = response.json()
    # TODO remove me - debug only to see what values we get from the api call
    #pprint.pprint(pull_content)

    base_ref = pull_content["base"]["ref"]
    # This is the same as $COMMIT_ID in previous jenkins workflow
    base_sha = pull_content["base"]["sha"]
    base_url = pull_content["base"]["repo"]["git_url"]
    remote_ref = pull_content["head"]["ref"]
    remote_sha = pull_content["head"]["sha"]
    remote_url = pull_content["head"]["repo"]["git_url"]
    test_branch_name = "tpr-" + remote_ref + "_" + pull_content['user']['login']

    #TODO
    # Should we be building an image where we pull the latest in the build, or should we just be doing all the work here?
    # We could clone the repo in the build, then pull here to reduce work a very small amount
    run_cli_cmd(['/usr/bin/git', 'clone', base_url])

    prev_dir = os.getcwd()
    os.chdir("openshift-tools")
    run_cli_cmd(['/usr/bin/git', 'checkout', '-b', test_branch_name])
    run_cli_cmd(['/usr/bin/git', 'pull', remote_url, remote_ref])
    run_cli_cmd(['/usr/bin/git', 'pull', remote_url, remote_ref, '--tags'])
    run_cli_cmd(['/usr/bin/git', 'checkout', base_ref])
    run_cli_cmd(['/usr/bin/git', 'merge', test_branch_name])

    # Run the python linter on any changed python files
    linter(base_sha, remote_sha)
    # Run yaml validation on any yaml files
    validate_yaml(base_sha, remote_sha)
    # If this pull request is submitting to prod, ensure the stage branch already contains this commit
    if base_ref == PROD_BRANCH_NAME:
        ensure_stg_contains(remote_sha)

    if len(Errors) > 0:
        for e in Errors:
            print("ERROR: " + e)
        sys.exit(1)

if __name__ == '__main__':
    main()
