
namespace :ci do
  namespace :deploy do
    desc 'Initialize new environment on the Puppet server'
    task :init do
      env_dir = "/etc/puppetlabs/code/environments/#{@config['remote_dir']}"
      cmd = []
      cmd << "ssh -tt #{@config['user']}@#{@config['server']} 'mkdir -p #{env_dir}"
      cmd << "git clone git@git-nc.nomadrail.com:env/environment-#{@config['env']}.git #{env_dir}/"
      cmd << "cd #{env_dir}"
      cmd << "git checkout #{@config['branch']}" unless @config['branch'] == 'master'
      cmd << "git pull --rebase origin #{@config['branch']}"
      cmd << "git submodule update --init"
      cmd << "/opt/puppetlabs/bin/puppet generate types --environment #{@config['remote_dir']} --force'"
      puts `#{cmd.join(' && ')}`
    end
    desc 'Deploy environment to the Puppet server'
    task :remote do
      env_dir = "/etc/puppetlabs/code/environments/#{@config['remote_dir']}"
      cmd = "ssh -tt #{@config['user']}@#{@config['server']} " \
            "'cd #{env_dir} && " \
            "nd-update-puppetenv.sh #{@config['branch']}'"
      puts `#{cmd}`
    end
    desc 'Destroy environment on the Puppet server'
    task :destroy do
      env_dir = "/etc/puppetlabs/code/environments/#{@config['remote_dir']}"
      cmd = []
      cmd << "ssh -tt #{@config['user']}@#{@config['server']}"
      cmd << "'rm -rf #{env_dir}'"
      puts `#{cmd.join(' ')}`
    end
  end
end
# -*- mode: ruby -*-
# vi: set ft=ruby :
