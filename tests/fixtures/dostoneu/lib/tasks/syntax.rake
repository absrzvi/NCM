require 'colorize'
require 'json'
require 'puppet'
require 'puppet/face'
require 'puppet/test/test_helper'
require 'yaml'

desc 'Validate syntax for Puppet and Hiera'
task :syntax do
  Puppet::Test::TestHelper.initialize
  error = []

  Dir.glob(
    [
      "#{Dir.pwd}/hiera.yaml",
      "#{Dir.pwd}/hieradata/**/*.json",
      "#{Dir.pwd}/hieradata/**/*.yaml",
      "#{Dir.pwd}/manifests/**/*.pp",
      "#{Dir.pwd}/modules/**/*.pp"
    ]
  ).sort.uniq.each do |f|
    begin
      case f
      when %r{/spec/fixtures}
        next
      when /.yaml$/
        YAML.load_file(f)
      when /.pp$/
        Puppet::Face[:parser, :current].validate(f)
      when /.json$/
        JSON.parse(File.read(f))
      end

      puts f.gsub(%r{.*environments/}, '')
    rescue SystemExit => _e
      error << "Failed to parse #{f.gsub(%r{.*environments/}, '')}"
    end
  end

  unless error.empty?
    error.each { |e| puts e.colorize(:red) }
    exit 1
  end
end

# -*- mode: ruby -*-
# vi: set ft=ruby :
