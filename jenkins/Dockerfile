FROM centos

RUN yum install -y git python
RUN git clone https://github.com/tiwillia/openshift-tools /root/openshift-tools
RUN curl https://raw.githubusercontent.com/openshift/openshift-ansible/master/git/yaml_validation.py -o /root/yaml_validation.py

WORKDIR /root/
COPY * /root/

USER 1001
ENTRYPOINT ["python", "/root/openshift-tools/jenkins/run_pr_validation.py"]
