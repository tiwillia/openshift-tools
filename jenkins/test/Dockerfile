FROM registry.ops.openshift.com/ops/oso-rhel7-host-monitoring:prod

# Add the openshift bot credentials to the build
ADD openshift-ops-bot/ /openshift-ops-bot/

RUN mkdir /validator && \
    git clone https://github.com/tiwillia/openshift-tools /validator/openshift-tools && \
    cd /validator/openshift-tools && \
    git config user.name validator && \
    git config user.email validator@localhost && \
    git checkout lint_in_container


# Set this so that the image, when started, will automaticall sit and sleep
# for debugging purposes
ENV OO_PAUSE_ON_START=true

RUN cd /validator/openshift-tools/ && /usr/bin/python /validator/openshift-tools/jenkins/test/run_tests.py
