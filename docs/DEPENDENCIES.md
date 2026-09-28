# Dependency/license review

Reviewed 2026-09-06 for internal commercial use.

| Component | Pin | License / role |
|---|---|---|
| LiteLLM Proxy | v1.99.1 + Compose digest | MIT core; separate enterprise terms; provider protocols |
| Python | 3.12 image | PSF; runtime |
| FastAPI | 0.141.1 | MIT; API |
| Starlette | 1.3.1 | BSD-3-Clause; focused fix for scanner-reported HIGH advisories |
| Uvicorn | 0.52.4 | BSD-3-Clause; ASGI |
| HTTPX | 0.28.1 | BSD-3-Clause; transport |
| Pydantic | 2.13.5 | MIT; validation |
| PyYAML | 6.0.3 | MIT; safe configuration |
| jsonschema | 4.26.0 | MIT; generated output validation |
| SQLite | standard library | Public domain engine; durable journal |

Versions/licenses checked against official PyPI metadata and LiteLLM tagged sources.
Runtime transitive dependencies are version/hash locked in requirements.lock. Dev tools
are pinned in pyproject.toml; their transitive resolution is separate. Preserve notices when
redistributing images. Provider API terms and model weight licenses remain separate; disabled
examples do not establish commercial inference entitlement.

Sources: [LiteLLM license](https://raw.githubusercontent.com/BerriAI/litellm/v1.99.1/LICENSE),
[release](https://github.com/BerriAI/litellm/releases/tag/v1.99.1),
[FastAPI](https://pypi.org/pypi/fastapi/0.141.1/json),
[Uvicorn](https://pypi.org/pypi/uvicorn/0.52.4/json),
[HTTPX](https://pypi.org/pypi/httpx/0.28.1/json),
[Pydantic](https://pypi.org/pypi/pydantic/2.13.5/json),
[PyYAML](https://pypi.org/pypi/PyYAML/6.0.3/json),
[jsonschema](https://pypi.org/pypi/jsonschema/4.26.0/json),
[Python](https://docs.python.org/3/license.html), [SQLite](https://sqlite.org/copyright.html).

Before deployment/upgrades, verify image signatures with release's commit-pinned cosign key,
scan dependencies/images, review advisories and rerun proxy contract tests. Digest pinning
prevents tag drift; it is not proof of a safe image. A complete transitive license/security
audit has not been claimed. See CURRENT_STATE for verification actually performed.
The 2026-09-07 signature and vulnerability outcomes, evidence and required dispositions are
recorded in RELEASE_GATES.md. A valid image signature does not imply a vulnerability-free image.
