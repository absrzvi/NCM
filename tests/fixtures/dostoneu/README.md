# Introduction

This Nomad Connect environment is the target environment that will be released quarterly in order for it to be used by QA, devops, etc. It is intended to be a basis for testing by QA or to be forked for a new project.

# Installation guide

To install this reference release, please ensure that you have obtained a "base image". This base image contains a stripped copy of Debian along with a set of installation scripts.

Fire up the base image and log in as user developer. To start the installation, run the `autoinstall.sh` script. After a few initial checks, you will be prompted for a set of installation parameters:

* project name: `dostoneu-<train_type>`
* project id: `50` or `51`
* rtl project id: `50` or `51`
* train id: a free train id (Ask Project Engineer responsible for the project)
* rtl train id: same as train id
* unit id: `1`

After this, the system will start the puppet installation inside the squashfs. When this puppet installation has completed, a new squashfs filesystem will be prepared and set up to start after the system has rebooted.

# TRAIN_TYPE
Available Traintypes are:
* `dostoneu-fv5` aka Fernverkehr 5-Coach
* `dostoneu-fv6` aka Fernverkehr 6-Coach
* `dostoneu-nv4` aka Nahverkehr 4-Coach
* `dostoneu-nv6` aka Nahverkehr 6-Coach

# Problems

In case of any issues or questions, please contact an R&D team member on [Slack](https://nomad-digital.slack.com).
