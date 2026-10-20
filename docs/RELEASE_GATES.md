# Focused release gates — 2026-09-07

Production release: BLOCKED pending vulnerability disposition. No uncontrolled dependency upgrades,
production changes or automatic acceptance of advisories occurred. Scanner findings are evidence,
not a proof of exploitability. Raw JSON and tool outputs remain under ignored `.runtime/acceptance/`.

## Image identity and signature

LiteLLM v1.99.1 is pinned to `sha256:a53a7d3ffebede1925bd3ee8a21e4a7b9b63e2e68ec883af136edcccb6eeb82c`.
Cosign v3.1.3 verified the signature against the upstream public key at commit
`0112e53046018d726492c814b3644b7d376029d0`, including offline transparency-log inclusion.
The Cosign binary checksum matched the official release checksum. Evidence: litellm-signature.json
and litellm-signature-status.txt. This verifies the selected key/signature, not absence of vulnerabilities.

Gateway base: official Python 3.12.13-slim-bookworm, now pinned to manifest digest
`sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2`.
Its digest was resolved from the official Docker image; an independent Python base signature is not claimed.

Trivy 0.74.0 scanned the actual local images. Docker Scout required login and was not a passing scan.
pip-audit 2.9.0 stalled without producing a report and was stopped; it is BLOCKED, not PASS.
Trivy provides the completed runtime Python/OS vulnerability evidence.

## Image findings

### litellm: {'HIGH': 1} package/advisory records

| Severity / advisory | Packages | Fixed version reported |
|---|---|---|
| HIGH / CVE-2026-82397 | tornado | 6.5.8 |

### gateway: {'HIGH': 55, 'CRITICAL': 5} package/advisory records

| Severity / advisory | Packages | Fixed version reported |
|---|---|---|
| HIGH / CVE-2026-53613 | bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount, util-linux, util-linux-extra | not supplied for this distro/package |
| HIGH / CVE-2026-76642 | bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount, util-linux, util-linux-extra | not supplied for this distro/package |
| HIGH / CVE-2026-78408 | bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount, util-linux, util-linux-extra | not supplied for this distro/package |
| HIGH / CVE-2026-78409 | bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount, util-linux, util-linux-extra | not supplied for this distro/package |
| HIGH / CVE-2026-78410 | bsdutils, libblkid1, libmount1, libsmartcols1, libuuid1, mount, util-linux, util-linux-extra | not supplied for this distro/package |
| HIGH / CVE-2026-41992 | gzip | not supplied for this distro/package |
| HIGH / CVE-2026-54369 | libacl1 | not supplied for this distro/package |
| HIGH / CVE-2025-69720 | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | not supplied for this distro/package |
| CRITICAL / CVE-2025-7458 | libsqlite3-0 | not supplied for this distro/package |
| HIGH / CVE-2026-11822 | libsqlite3-0 | not supplied for this distro/package |
| HIGH / CVE-2026-11824 | libsqlite3-0 | not supplied for this distro/package |
| HIGH / CVE-2026-16742 | libsystemd0, libudev1 | not supplied for this distro/package |
| CRITICAL / CVE-2026-13221 | perl-base | not supplied for this distro/package |
| CRITICAL / CVE-2026-42496 | perl-base | not supplied for this distro/package |
| CRITICAL / CVE-2026-8376 | perl-base | not supplied for this distro/package |
| HIGH / CVE-2026-42497 | perl-base | not supplied for this distro/package |
| HIGH / CVE-2026-48962 | perl-base | not supplied for this distro/package |
| HIGH / CVE-2026-57432 | perl-base | not supplied for this distro/package |
| HIGH / CVE-2026-57433 | perl-base | not supplied for this distro/package |
| HIGH / CVE-2026-9538 | perl-base | not supplied for this distro/package |
| CRITICAL / CVE-2023-45853 | zlib1g | not supplied for this distro/package |

The gateway originally carried Starlette 0.47.3 with three HIGH findings. A focused pin to
1.3.1 addresses the scanner-reported fixed versions and meets installed FastAPI constraints.
Only Starlette changed in the runtime lock resolution. Gateway regression tests and the
real LiteLLM/mock-provider contract are rerun for this security fix.

CVE-2023-45853 is reported CRITICAL against Debian zlib. The
[Debian tracker](https://security-tracker.debian.org/tracker/CVE-2023-45853)
says Bookworm does not build the affected contrib/minizip binary. Treat that record as
a distro applicability finding to document, not evidence that the MG JSON endpoint exposes MiniZip.
Other OS HIGH findings still need package-specific disposition. Non-root, read-only filesystems,
dropped capabilities and no file-serving/tool execution reduce exposure but are not a blanket waiver.

LiteLLM tornado 6.5.7 has HIGH CVE-2026-82397, fixed in 6.5.8. Prefer an upstream signed
image with the fix; review its digest and rerun the proxy contract before promotion. Do not patch
the running container or silently upgrade the entire proxy stack.

## Consumer dependency audits

### portal: {'info': 0, 'low': 0, 'moderate': 5, 'high': 4, 'critical': 1, 'total': 10}

| Package | Severity | Direct advisory evidence / dependency chain |
|---|---|---|
| @prisma/config | high | deepmerge-ts |
| deepmerge-ts | high | [DeepmergeTS has stack exhaustion when merging recursive object graphs](https://github.com/advisories/GHSA-ggr8-5vv4-36mx) |
| prisma | high | @prisma/config |
| vite | high | [Vite Vulnerable to Path Traversal in Optimized Deps `.map` Handling](https://github.com/advisories/GHSA-4w7w-66w2-5vf9); [launch-editor: NTLMv2 hash disclosure via UNC path handling on Windows](https://github.com/advisories/GHSA-v6wh-96g9-6wx3); [vite: `server.fs.deny` bypass on Windows alternate paths](https://github.com/advisories/GHSA-fx2h-pf6j-xcff); esbuild |
| vitest | critical | @vitest/mocker; [Vitest allows Remote Code Execution when accessing a malicious website while Vitest API server is listening](https://github.com/advisories/GHSA-9crc-q9x8-hgqq); [When Vitest UI server is listening, arbitrary file can be read and executed](https://github.com/advisories/GHSA-5xrq-8626-4rwp); vite; vite-node |

### website: {'info': 0, 'low': 4, 'moderate': 24, 'high': 7, 'critical': 0, 'total': 35}

| Package | Severity | Direct advisory evidence / dependency chain |
|---|---|---|
| @strapi/upload | high | qs; sharp |
| fast-uri | high | [fast-uri vulnerable to host confusion via skipped IDN canonicalization on scheme-relative references](https://github.com/advisories/GHSA-5jgf-p345-68v8); [fast-uri vulnerable to server-side request forgery via malformed IPv6 normalization](https://github.com/advisories/GHSA-f65p-4m7j-42xc); [fast-uri vulnerable to server-side request forgery via repeated hostname percent-decoding](https://github.com/advisories/GHSA-fph4-wmhf-6fwf); [fast-uri vulnerable to host confusion via percent-encoded scheme normalization](https://github.com/advisories/GHSA-jqff-g426-hqxp) |
| nanoid | high | [nanoid: custom generators can loop indefinitely when size is zero](https://github.com/advisories/GHSA-2v37-7h3g-55p8) |
| next | high | postcss; sharp |
| postcss | high | [PostCSS has XSS via Unescaped </style> in its CSS Stringify Output](https://github.com/advisories/GHSA-qx2v-qp2m-jg93); [PostCSS: Arbitrary file read and information disclosure via attacker-controlled sourceMappingURL in CSS comments](https://github.com/advisories/GHSA-6g55-p6wh-862q); [PostCSS: incomplete fix of GHSA-6g55-p6wh-862q — attacker-controlled sourceMappingURL reads arbitrary .map files when `from` is unset](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp); [PostCSS: Path Traversal in Previous Source Map Auto-Loading (sourceMappingURL) leads to Arbitrary .map File Disclosure](https://github.com/advisories/GHSA-r28c-9q8g-f849) |
| sharp | high | [sharp inherited vulnerabilities in libvips: CVE-2026-33327, CVE-2026-33328, CVE-2026-35590, CVE-2026-35591](https://github.com/advisories/GHSA-f88m-g3jw-g9cj) |
| vite | high | [Vite Vulnerable to Path Traversal in Optimized Deps `.map` Handling](https://github.com/advisories/GHSA-4w7w-66w2-5vf9); [launch-editor: NTLMv2 hash disclosure via UNC path handling on Windows](https://github.com/advisories/GHSA-v6wh-96g9-6wx3); [vite: `server.fs.deny` bypass on Windows alternate paths](https://github.com/advisories/GHSA-fx2h-pf6j-xcff); esbuild |

Portal: the critical Vitest finding affects development test API/UI server modes; this run used
`vitest run`. Select a verified fixed Vitest/Vite combination and rerun tests in a separate
bounded maintenance task. Prisma transitive deepmerge-ts also needs a supported fixed chain.
Do not follow npm suggestions that downgrade Prisma or move major versions without review.

Website: Next, sharp/upload and transitive parser/build dependencies have HIGH findings.
Runtime-reachable image/request handling requires explicit remediation before production release.
Do not automatically migrate Next major versions or downgrade Strapi to satisfy audit suggestions.

Existing Website PROJECT_STATUS.md contains a local database DSN with embedded credentials.
Value deliberately omitted here. Confirm validity, rotate if active, redact the document, and assess
history exposure in a separately scoped owner-controlled task. This integration did not modify it.

No credentials were committed, staged, sent to an inference provider or placed in the report.
Gateway secret/config checks pass; the existing Website documentation finding prevents a
blanket claim that every consuming repository is secret-free.
