""" Run all tests for openshift-tools repository """
# This script expects a single environment variable to be defined with a myriad of json data:
#    GITHUB_WEBHOOK_PAYLOAD
#
# The data expected from this payload is that generated by the pull reqeust edit webhook,
# defined here:
#    https://developer.github.com/v3/activity/events/types/#pullrequestevent
#
# The script will parse the JSON and define a list of environment variables for consumption by
# the validation scripts. Then, each *.py file in ./validators/ (minus specified exclusions)
# will be run. The list of variables defined is below:
#  Github stuff
#    PRV_TITLE         Title of the pull request
#    PRV_BODY          Description of the pull request
#    PRV_PULL_ID       ID of the pull request
#    PRV_PULL_URL      URL of the pull request
#
#  Base info
#    PRV_BASE_SHA      Current SHA of the target being merged into
#    PRV_BASE_REF      ref (usually branch name) of the base
#    PRV_BASE_LABEL    Base label
#    PRV_BASE_NAME     Full name of the base 'namespace/reponame'
#
#  Remote (or "head") info
#    PRV_REMOTE_SHA    Current SHA of the branch being merged
#    PRV_REMOTE_REF    ref (usually branch name) of the remote
#    PRV_REMOTE_LABEL  Remote label
#    PRV_REMOTE_NAME   Full name of the remote 'namespace/reponame'

import os
import json
import subprocess
import sys
import requests

EXCLUDES = [
    "common.py",
    "yaml_validation.py",
    ".pylintrc"
]
VALIDATOR_PATH = "jenkins/test/validators/"
GITHUB_API_URL = "https://api.github.com"
REPO = "openshift-tools"
#REPO_USER = "openshift"
REPO_USER = "tiwillia"

def run_cli_cmd(cmd, exit_on_fail=True):
    '''Run a command and return its output'''
    proc = subprocess.Popen(cmd, bufsize=-1, stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                            shell=False)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        print "Unable to run " + " ".join(cmd) + " due to error: " + stderr
        if exit_on_fail:
            sys.exit(proc.returncode)
        else:
            return False, stdout
    else:
        return True, stdout

def assign_env(pull_request):
    '''Assign environment variables base don github webhook payload json data'''
    # Github environment variables
    os.environ["PRV_TITLE"] = pull_request["title"]
    os.environ["PRV_BODY"] = pull_request["body"]
    os.environ["PRV_PULL_ID"] = pull_request["number"]
    os.environ["PRV_URL"] = pull_request["url"]

    # Base environment variables
    base = pull_request["base"]
    os.environ["PRV_BASE_SHA"] = base["sha"]
    os.environ["PRV_BASE_REF"] = base["ref"]
    os.environ["PRV_BASE_LABEL"] = base["label"]
    os.environ["PRV_BASE_NAME"] = base["repo"]["full_name"]

    # Remote environment variables
    head = pull_request["head"]
    os.environ["PRV_REMOTE_SHA"] = head["sha"]
    os.environ["PRV_REMOTE_REF"] = head["ref"]
    os.environ["PRV_REMOTE_LABEL"] = head["label"]
    os.environ["PRV_REMOTE_NAME"] = head["repo"]["full_name"]

def merge_changes(pull_request):
    """ Merge changes into current repository """
    remote_url = pull_request["head"]["repo"]["git_url"]
    remote_ref = pull_request["head"]["ref"]
    base_ref = pull_request["base"]["ref"]
    test_branch_name = "tpr-" + remote_ref + "-" + pull_request["number"]

    run_cli_cmd(['/usr/bin/git', 'checkout', base_ref])
    run_cli_cmd(['/usr/bin/git', 'checkout', '-b', test_branch_name])
    run_cli_cmd(['/usr/bin/git', 'remote', 'add', 'remoterepo', remote_url])
    run_cli_cmd(['/usr/bin/git', 'fetch', 'remoterepo', remote_ref])
    #run_cli_cmd(['/usr/bin/git', 'merge', 'remoterepo/' + remote_ref])
    run_cli_cmd(['/usr/bin/git', 'checkout', remote_ref])

def run_validators():
    """ Run all test validators """
    failure_occured = False
    validators = [validator for validator in os.listdir(VALIDATOR_PATH) if
                  os.path.isfile(os.path.join(VALIDATOR_PATH, validator))]
    for validator in validators:
        skip = False
        for exclude in EXCLUDES:
            if validator == exclude:
                skip = True
        if skip:
            continue
        validator_abs = os.path.join(VALIDATOR_PATH, validator)
        executer = ""
        _, ext = os.path.splitext(validator)
        if ext == ".py":
            executer = "/usr/bin/python"
        elif ext == ".sh":
            executer = "/bin/sh"
	# If the ext is not recongized, try to just run the file
        print "Running " + executer + " " + validator_abs
        success, output = run_cli_cmd([executer, validator_abs], exit_on_fail=False)
        print output
        if not success:
            print validator + " failed!"
            failure_occured = True

    if failure_occured:
        return False
    return True

def submit_pr_comment(text, pull_id):
    """ Submit a comment on a pull request or issue in github """
    github_username, oauth_token = get_github_credentials()
    payload = {'body': text}
    comment_url = "%s/repos/%s/%s/issues/%s/comments" % (GITHUB_API_URL, REPO_USER, REPO, pull_id)
    response = requests.post(comment_url, json=payload, auth=(github_username, oauth_token))
    # Raise an error if the request fails for some reason
    response.raise_for_status()

def get_github_credentials():
    """ Get credentials from mounted secret volume """
    secret_dir = os.getenv("OPENSHIFT_BOT_SECRET_DIR")
    if secret_dir == "":
        print "ERROR: $OPENSHIFT_BOT_SECRET_DIR undefined. This variable should exist and" + \
            " should point to the mounted volume containing the openshift-ops-bot username" + \
            " and password"
        sys.exit(2)
    username_file = open(os.path.join("/", secret_dir, "username"), 'r')
    token_file = open(os.path.join("/", secret_dir, "token"), 'r')
    username = username_file.read()
    username_file.close()
    token = token_file.read()
    token_file.close()
    return username, token

def main():
    """ Get the payload, merge changes, assign env, and run validators """
    payload_json = os.getenv("GITHUB_WEBHOOK_PAYLOAD", "")

    if payload_json == "":
        print 'No JSON data provided in $GITHUB_WEBHOOK_PAYLOAD'
        sys.exit(1)
    try:
        payload = json.loads(payload_json, parse_int=str, parse_float=str)
    except ValueError:
        print "Unable to load JSON data from $GITHUB_WEBHOOK_PAYLOAD"
        sys.exit(1)
    pull_request = payload["pull_request"]

    # Merge changes from pull request
    merge_changes(pull_request)
    # Assign env variables for validators
    assign_env(pull_request)

    # Run validators
    success = run_validators()
    pull_id = pull_request["number"]
    if not success:
        submit_pr_comment("Tests failed!", pull_id)
        sys.exit(1)
    submit_pr_comment("Tests passed!", pull_id)

if __name__ == '__main__':
    main()
