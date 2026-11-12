# Security

## Reporting a problem

If you find a security problem in N-antibot (for example, a way to make it block legitimate visitors, to bypass the
API token, or to make the installer damage a configuration), please **do not publish the details in a public
issue**.

Open an [issue](https://github.com/KrilinZ/N-antibot/issues) that only says you have a security report, without
details, and the maintainer will arrange a private channel with you.

## What to expect

N-antibot is an open-source project with no guaranteed response time, but security reports are looked at before
anything else.

## Scope and design notes

- The generator and the report run on your machine and send nothing anywhere. Their only network use is downloading
  public routing data from RIPEstat.
- The API (`n-antibot serve`) is read-only, listens on `127.0.0.1` by default and refuses to listen elsewhere
  without a token. It returns visitors' IP addresses: protect it accordingly.
- The installer backs up every file it touches and restores it if validation, reload or the live check fails.
- Blocking by network and User-Agent is not a complete defence. See "Limits" in the README.
