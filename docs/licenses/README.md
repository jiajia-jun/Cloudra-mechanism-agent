# Copyright and licenses

Cloudra is licensed under the [GNU Affero General Public License v3.0 or later](../../LICENSE).

Copyright (C) 2026 Cloudra Team.

## Skills are MIT

The skills under [`cloudra/skills/`](../../cloudra/skills/) are a deliberate exception to
the project license. Each one declares `license: MIT` in its frontmatter and is licensed
under the MIT License.

The reason is portability. Skills are reusable knowledge rather than engine code: they are
written to be adopted by other agent harnesses and other projects, and a permissive license
is what makes that adoption frictionless. The engine, the DAG, the tools, the scheduler and
everything else remain AGPL — the copyleft protects the system, the permissive license
spreads the knowledge.

A skill adapted from an upstream project keeps its upstream terms; those are recorded
below. The `humanizer` skill is third-party MIT and is not Cloudra's to license at all.

## Third-party components

Third-party components bundled in this repository keep their own licenses and are listed
below. The repository's root `LICENSE` remains the project license.

- [autodE numerical references and license](autode-derived-code.md): attribution for derived optimizer code
- [humanizer skill and license](humanizer-skill.md): vendored MIT-licensed skill by Siqi Chen
- [ASE skill references and license](ase-skill-references.md): MIT-licensed references adapted from jkitchin/skillz
- [K-Dense scientific-agent-skills and license](k-dense-scientific-agent-skills.md): MIT-licensed `molecular-dynamics` skill adapted into `molecular-dynamics-simulation`

Keep third-party permission notices here with the code that requires them. A notice is
required whenever a file is copied from or adapted from an upstream project: the upstream
copyright line and the full upstream permission text must both be preserved, and the
adapted file must state its upstream path.

Attribution that lives only in an editable field will eventually be deleted by a rewrite.
When adding an adapted skill, put the upstream project, upstream path, license and
copyright line in the skill frontmatter `metadata` block **and** record the full upstream
permission notice here.
