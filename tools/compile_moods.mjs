#!/usr/bin/env node
// Compiles moods/*.json against assets/rig.json and prints {"css", "registry", "poses"} as JSON.
//
//   node tools/compile_moods.mjs [--moods DIR] [--rig PATH]
//
// Exits 1 with a list of problems on schema errors. Used by tools/build_whale_chan.py.
import { readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { buildRegistry, compileCss, resolvePose, sortMoods, validate } from "./moods.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 && args[i + 1] ? resolve(args[i + 1]) : fallback;
};
const moodsDir = opt("--moods", join(root, "moods"));
const rigPath = opt("--rig", join(root, "assets", "rig.json"));

function fail(lines) {
  process.stderr.write(`compile_moods: ${[].concat(lines).join("\n  ")}\n`);
  process.exit(1);
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (err) {
    fail(`${path}: ${err.message}`);
  }
}

const rig = readJson(rigPath);
const ctx = { rig, defaults: readJson(join(moodsDir, "_defaults.json")), keyframes: readJson(join(moodsDir, "_keyframes.json")) };
const files = readdirSync(moodsDir).filter((f) => f.endsWith(".json") && !f.startsWith("_")).sort();
const moods = files.map((f) => readJson(join(moodsDir, f)));

const errors = validate(moods, ctx);
moods.forEach((m, i) => {
  if (m.name !== basename(files[i], ".json")) errors.push(`${files[i]}: "name" must match the file name`);
});
if (!moods.length) errors.push(`no moods found in ${moodsDir}`);
if (errors.length) fail(["invalid mood data:", ...errors]);

const poses = {};
for (const m of sortMoods(moods)) {
  poses[m.name] = resolvePose(m, ctx);
  for (const v of Object.keys(m.variants || {})) if (m.variants[v].pose?.arms) poses[`${m.name}/${v}`] = resolvePose(m, ctx, v);
}
process.stdout.write(JSON.stringify({ css: compileCss(moods, ctx), registry: buildRegistry(moods), poses }));
