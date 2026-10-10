// Generate packages/shared-types/src/generated.ts from the v1 JSON Schema bundle.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schemaPath = resolve(root, "packages/event-schema/schemas/v1/tari.schema.json");
const out = resolve(root, "packages/shared-types/src/generated.ts");
const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
const version = readFileSync(resolve(root, "packages/event-schema/schemas/v1/VERSION"), "utf8").trim();

// Pydantic emits `title` on every property, which would create one alias per field. Drop property titles.
function stripTitles(node, isDefRoot = false) {
  if (Array.isArray(node)) return node.forEach((n) => stripTitles(n));
  if (!node || typeof node !== "object") return;
  if (typeof node.$ref === "string") {
    // A $ref with sibling keys (description/default) would become a duplicate named type.
    for (const k of Object.keys(node)) if (k !== "$ref") delete node[k];
    return;
  }
  if (!isDefRoot && "title" in node && node.type !== "object") delete node.title;
  for (const [k, v] of Object.entries(node)) {
    if (k === "$defs") for (const d of Object.values(v)) stripTitles(d, true);
    else stripTitles(v);
  }
}
stripTitles(schema, true);

const ts = await compile(schema, "TariSchemaV1", {
  bannerComment: `/* eslint-disable */\n/**\n * Generated from packages/event-schema/schemas/v1/tari.schema.json (schema ${version}).\n * Do not edit by hand: run \`pnpm gen:schema\`.\n */`,
  additionalProperties: false,
  unreachableDefinitions: true,
  strictIndexSignatures: false,
  maxItems: -1,
  format: true,
});
writeFileSync(out, `${ts}\nexport const SCHEMA_VERSION = "${version}";\n`);
console.log(`wrote ${out}`);
