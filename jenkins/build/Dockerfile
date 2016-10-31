FROM registry.ops.openshift.com/ops/oso-rhel7-host-monitoring:prod

RUN mkdir /validator && \
    git clone https://github.com/tiwillia/openshift-tools /validator/openshift-tools && \
    cd /validator/openshift-tools && \
    git config user.name validator && \
    git config user.email validator@localhost && \
    git checkout lint_in_container && \
    # Get latest yaml validation script from openshift-ansible repository
    curl https://raw.githubusercontent.com/openshift/openshift-ansible/master/git/yaml_validation.py -o /validator/openshift-tools/jenkins/validators/yaml_validation.py && \
    # Fix permissions so we can write to this directory later on
    chown -R 1001:0 /validator && \
    find /validator -exec chgrp 0 {} \; && \
    find /validator -exec chmod g+rw {} \; && \
    find /validator -type d -exec chmod g+x {} +

WORKDIR /validator/openshift-tools

USER 1001

ENV OO_PAUSE_ON_START=true
