---
attention: historical
---
# Google Docs inline image repair
Historical record. Closed 2026-11-20. Slug: `google-docs-images`. Maintained commands and safeguards belong to [Google Docs](../../use-google-docs/SKILL.md). The bounded image-repair capability is implemented, published and independently checked; document-specific visual acceptance, wider platforms and interrupted-upload recovery are not claimed.

The retained development entries describe their dated checkpoints; later pending or local-only statements are historical.

Extend the native Docs capability with bounded image inspection and revision-guarded replacement of existing inline image placements. Preserve surrounding text and native structure. Local PNG, JPEG and GIF files use a temporary private Google Doc import in an explicitly selected Drive folder; use its short-lived image content URIs and trash only the import created by this operation. No sharing changes, arbitrary API dispatch, credential changes or document-body rewrites are included.

Replacement reinserts one inline image at its exact existing index with an explicit display width and source aspect ratio. It changes that image object ID and does not preserve image-specific cropping/effects; reject ambiguous placements and pending native suggestions. Preview fingerprints bind the account, document revision, image positions, local source hashes, widths and temporary folder. Required revisions protect the write. Independent readback verifies unchanged text and unaffected image bytes, expected replacement image content and cleanup.

Official schema: https://developers.google.com/workspace/docs/api/reference/rest/v1/documents/request#InsertInlineImageRequest and https://developers.google.com/workspace/docs/api/reference/rest/v1/documents#ImageProperties. Domain decisions and private live inputs stay outside this repository.
