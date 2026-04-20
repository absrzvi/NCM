# Introduction

This Nomad Connect environment is the blueprint environment that will be used as a basis for every new project. The Nomad Connect team will update it to the latest quarterly release and maintain the agreed default parameters for any future projects.

This environment is not intended to be used for any CCUs, just to be forked into new environments. Only R&D will do a clean install of this environment when updating to verify it was updated properly.

# Usage

Follow this guide to quickly get your environment up and running:

* Clone the blueprint environment into a new local clone with `git clone git@vmgitlab01.ovh2.21net.com:env/environment-blueprint.git environment-xxx`, where `xxx` is your new environment name.
* Create a new environment in gitlab called `environment-xxx`
* In your newly cloned environment (`cd environment-xxx`) remove the remote with `git remote remove origin`
* Set a new origin with `git remote add origin git@git-nc.nomadrail.com:env/environment-xxx.git`
* Remove any remaining blueprint hieradata files with `git rm hieradata/nodes/box1-t*.blueprint.*`
* Edit the `Rakefile` and change any references to `blueprint` to the name of your new environment
* Commit these changes with `git add -A; git commit -m "blueprint cloning"`
* (Optional) you might want your git history to start with a "clean slate" where you compress all the previous blueprint commits into one, this can be done with `git rebase -i --root`; you then select "fixup" for all commits after the initial commit.
* Push your environment to gitlab with `git push --set-upstream origin master`
* You now have a master branch on your environment with a working blueprint setup!
* You can deploy this environment/branch to the puppet master with `rake ci:deploy:init`.

# Problems

In case of any issues or questions, please contact an R&D team member on [Slack](https://nomad-digital.slack.com).
