#!/usr/bin/env node
// Microsoft setup owns establishing the separate browser identity and document-scoped add-in startup.
import {main} from '../../use-word-documents/scripts/main.mjs';
await main(process.argv.slice(2), true);
