import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const read = (relative) => fs.readFileSync(path.join(site, "public", relative), "utf8")

test("the compiled guide preserves Chinese, mathematics and source navigation", () => {
  const html = read("guide/quickstart.html")
  assert.match(html, /使用指南/)
  assert.match(html, /katex/)
  assert.match(html, /papers/)
  assert.match(html, /research/)
  assert.match(html, /search/)
  assert.match(html, /backlinks/)
  assert.doesNotMatch(html, /fonts\.googleapis\.com/)
  assert.doesNotMatch(html, /plausible\.io/)
})

test("the compiled site contains a real homepage and a client search index", () => {
  assert.match(read("index.html"), /具身智能/)
  const index = JSON.parse(read("static/contentIndex.json"))
  assert.ok(index["guide/quickstart"], "guide is included in client-side search")
})
