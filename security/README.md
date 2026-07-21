# Credential boundary

The existing Alibaba Bailian Demo API Key is an explicit user-authorized exception for this private repository.
It remains versioned only in `backend/.env.demo` so the same private revision works on both development Macs.
The user explicitly chose not to rotate or revoke it and accepts the disclosure risk.

`scripts/test-secrets.sh` fingerprints the authorized value without printing it. The same fingerprint may exist
in Git history only; it must not appear in any other current source file, log, Trace, backend archive, frontend
bundle, or test artifact. No other API Key, Token, Cookie, password, or production credential is authorized for
version control.
