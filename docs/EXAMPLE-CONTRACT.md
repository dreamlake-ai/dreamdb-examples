# External application example contract

This repository demonstrates applications **using** DreamDB. It is not an SDK,
a plugin framework, a shared application runtime, or a promise to maintain
each prototype as a product. Robotics is one domain, not the repository's scope.

An application owns its domain model, input interpretation, transformations,
workflow and UI. DreamDB owns its storage/query/versioning contracts. Install
application dependencies because the chosen application needs them; do not
make unrelated examples or ordinary DreamDB users install them.

Every example's README must identify:

1. The user problem, input, output and the actual DreamDB APIs/capabilities used.
2. The application/storage boundary and the reusable design decisions.
3. Its status: **validated reference**, **experimental**, **legacy/unverified**,
   or **companion** (not itself a DreamDB application). Validation is scoped,
   not a production-readiness label.
4. Tested SDK version or source commit, application dependencies and platform
   requirements. Distinguish tested builds from released packages.
5. One smallest runnable path, then optional full application instructions.
   Name external services, hardware, credentials/configuration and generated
   artifacts explicitly. Never commit credentials or private source data.
6. One direct observable success criterion at the real application boundary,
   limitations, measured costs if any, and cleanup instructions.

Keep alternative experiments behind an index. Preserve their original pins and
results; do not relabel historical measurements as results of today's main.
Do not build a second framework to validate the acceptance tooling. When an
example discovers a DreamDB defect, report it to core rather than disguising
an internal workaround as the recommended application API.
