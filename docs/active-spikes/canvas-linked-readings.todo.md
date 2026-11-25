---
attention: live
reviewed: 2026-11-25
---
# Canvas linked readings tasks
[Scope and choices](canvas-linked-readings.md). Opened 2026-11-25. Slug: `canvas-linked-readings`.

## To Do
- [ ] The user checks that known readings appear with the right category, title and place.
- [ ] Decide whether to add the optional local-file check.

## Done
- [x] Update the README's Canvas row, 2026-11-25.
- [x] List body and module links from an existing export with their category, source, modules and, for Canvas files, whether the export holds the file's metadata.
- [x] Keep access-bearing parts out: the export already strips them, and the inventory never opens an address.
- [x] Four synthetic tests cover categories, tables and lists, module links, missing files, in-page jumps, unchanged exports, missing accounts and refused inputs.
- [x] Try it on real exports. Listed four existing local exports offline on 2026-11-25, with totals matching an independent count of their body and module links. It found module links that point back into Canvas labelled as outside, now fixed with a test, and showed that a course whose pages are denied can list only its other areas, which the coverage line says.
