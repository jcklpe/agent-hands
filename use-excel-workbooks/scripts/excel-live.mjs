#!/usr/bin/env node
import {main} from '../live/main.mjs';
await main(process.argv.slice(2));
