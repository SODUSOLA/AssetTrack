// macOS only: keep node_modules out of iCloud Drive.
//
// This project lives in ~/Documents, which iCloud syncs and offloads. Tens of thousands of
// dependency files in there get uploaded, and once offloaded they hang every tool that reads
// them. iCloud ignores anything ending in ".nosync", so the real folder is node_modules.nosync
// and node_modules is a symlink to it. npm replaces the symlink with a real folder on every
// install, so this runs again from the "postinstall" hook. On Linux (Docker, CI) it does nothing.
import { existsSync, lstatSync, renameSync, rmSync, symlinkSync } from "node:fs";

if (process.platform !== "darwin") process.exit(0);

const link = "node_modules";
const real = "node_modules.nosync";
if (!existsSync(link)) process.exit(0);
if (lstatSync(link).isSymbolicLink()) process.exit(0);

rmSync(real, { recursive: true, force: true });
renameSync(link, real);
symlinkSync(real, link);
console.log(`${link} moved to ${real} (kept out of iCloud) and symlinked back.`);
