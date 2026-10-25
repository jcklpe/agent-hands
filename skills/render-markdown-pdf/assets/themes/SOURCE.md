# Theme sources
`resume.css` is the unmodified public `aslan-resume.css` from [jcklpe/typora-resume-theme](https://github.com/jcklpe/typora-resume-theme/blob/main/aslan-resume.css), retrieved and compared on 2026-10-24. Its Git blob identifier is `aba5856fa69a1ca29eccac10b2bfe4b2c778b73f`; the previous configs copy matched exactly. The upstream [license](https://github.com/jcklpe/typora-resume-theme/blob/main/LICENSE) is GNU AGPL version 3. The collection includes that license in its root LICENSE. Preserve this provenance when distributing the theme alone. No personal document content is included.

`plain.css` is an original general-document baseline under this collection's AGPL-3.0-only license. It is not an approved academic-paper style or citation standard. Neither theme bundles fonts; installed fonts and fallback selection affect pagination.

`compact.css` preserves the existing configs compact/letter variant's 0.6-inch margin, now importing the résumé CSS instead of duplicating it. The previous `aslan-letter.css` and generated `aslan-compact.css` both express this same variant. Their old paths remain compatibility links in configs. Unlike the previous temporary-HTML pipeline, stylesheet-relative imports now resolve correctly.

Keep local adaptations explicit when comparing a future upstream version. This migration preserves the résumé appearance; redesigning it or adopting a formal academic theme is separate work.
