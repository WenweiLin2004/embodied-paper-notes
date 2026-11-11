# Third-party provenance

This site's renderer vendors **Quartz 5.1.0** from
[jackyzha0/quartz](https://github.com/jackyzha0/quartz).

- Upstream branch at import: `v5`
- Exact source commit: `7cfb0796165c848be5438117e9806802123bf676`
- Imported on: 2026-11-11
- Source archive: <https://github.com/jackyzha0/quartz/archive/7cfb0796165c848be5438117e9806802123bf676.zip>
- License: MIT; the original notice is retained in `LICENSE.txt`.
- Imported: `quartz/`, `quartz.ts`, TypeScript definitions/configuration,
  default YAML configuration, package manifest and npm lockfile.
- Omitted: upstream documentation, sample content, release workflows, Docker
  configuration, and Git history. There is no nested Git repository.

Local adaptations are limited to `quartz.config.yaml`,
`quartz/styles/custom.scss`, npm scripts, `.node-version`, `.gitignore`,
`tests/site-contract.test.mjs`, optional pnpm lock/build allowlist, and this provenance note. The core renderer
remains upstream source. Content comes from the repository's root `content/`
directory; generated output is `site/public/` and is never the source of truth.

Quartz community plugins and other npm dependencies retain their respective
licenses in their packages. `package-lock.json` pins the dependency graph for
`npm ci`. Use the fixed upstream commit when reviewing or updating vendor code.
The optional `pnpm-lock.yaml` records the dependency graph tested locally with
pnpm 11.25.0. Its native build allowlist is limited to esbuild and Parcel's
filesystem watcher. Keep using the same package manager/lockfile within a setup.

## Local commands

Requires Node.js >=22 (verified with 24.22.1) and npm >=10.9.2.

```sh
cd site
npm ci
npm run build
npm run test:site
npm run dev
```

The preview is normally at `http://localhost:8080`. `npm run build` consumes
`../content` and produces `public/`; it does not publish anything. Before
deployment, set `configuration.baseUrl` in `quartz.config.yaml` to
`<owner>.github.io/embodied-paper-notes` (or your chosen custom domain).
GitHub Pages is a static reading surface: paper ingestion and AI calls run in
the local pipeline, never in the browser. Do not put API keys in content or
frontend configuration.
