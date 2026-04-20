# Poor man's ENC.
lookup('classes', {merge => unique}).include

# Set default exec path.
Exec {
  path => [ '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' ]
}

Package {
  install_options => ['-o', 'Dpkg::Options::=--force-confnew', '--no-install-recommends'],
}

Apt::Pin <| |> -> Package <| |>
Apt::Source <| |> -> Package <| |>
Class['apt::update'] -> Package <| provider == 'apt' |>

Service {
  provider => systemd
}
