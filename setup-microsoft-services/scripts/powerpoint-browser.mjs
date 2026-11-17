#!/usr/bin/env node
// Microsoft setup owns the shared Office browser identity and presentation add-in startup.
import {main} from '../../use-powerpoint-presentations/scripts/main.mjs';
await main(process.argv.slice(2), true);
