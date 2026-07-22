# Credential boundary

The existing Alibaba Bailian Demo API Key is an explicit user-authorized exception for this private repository.
It remains versioned only in `backend/.env.demo` so the same private revision works on both development Macs.
The user explicitly chose not to rotate or revoke it and accepts the disclosure risk.

`scripts/test-secrets.sh` fingerprints the authorized value without printing it. The same fingerprint may exist
in Git history only; it must not appear in any other current source file, log, Trace, backend archive, frontend
bundle, or test artifact. No other API Key, Token, Cookie, password, or production credential is authorized for
version control.

`scripts/security-scan.sh` is the local authoritative SAST, filesystem, IaC, and first-party image gate. The
applied employee default-model migration contains repository-owned static SQL and parameterized external values;
its two Semgrep SQLAlchemy findings were manually reviewed in S10-08. The gate verifies the exact SHA-256 recorded
in `semgrep-reviewed-static-sql.sha256`, excludes only that file from the clean pass, then rescans it and requires
the exact reviewed rule and line set. Any content or finding drift fails closed.

The same gate scans every runtime third-party image recorded in `third-party-images.json`. RAGFlow and its
officially pinned dependencies cannot be made into private derivative images under the project's zero-intrusion
rule. Their reviewed residual findings are therefore constrained by the exact upstream image digest, normalized
fixed High/Critical finding count and SHA-256, plus the private-network controls described in the baseline. A new
upstream image, vulnerability database result, package version, severity, or fix changes the normalized digest and
fails closed until the supported upstream release and production path are reviewed again.

The local RAGFlow Compose stack consumes the reviewed Elasticsearch, MySQL, MinIO, and Valkey digests directly;
the baseline scanner also targets those digests instead of mutable tags. If an upstream registry removes a digest,
the replacement must retain the reviewed architecture and be rescanned before both the stack and baseline move.
