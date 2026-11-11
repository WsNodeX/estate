# Security Policy

## Supported versions

Only the current `main` receives fixes.

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private reporting:
**Security** tab → **Report a vulnerability**.

## What this project handles

A GitHub token, read from the environment and never written anywhere. The token
needs only public read scope for the account being swept.

If you find a code path that logs the token, includes it in an error message, or
sends it anywhere other than `api.github.com`, that is the vulnerability this
policy most wants to hear about.

## Scope notes

- It sends unauthenticated-or-token-authenticated GET requests to the GitHub API.
  It does not write to any repository.
- It reads repository metadata only — no file contents except the
  `.github/ISSUE_TEMPLATE` directory listing.