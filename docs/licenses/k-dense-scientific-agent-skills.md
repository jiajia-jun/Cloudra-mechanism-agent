# K-Dense scientific-agent-skills (molecular-dynamics) and license

The `molecular-dynamics-simulation` skill is adapted from the `molecular-dynamics` skill of
[K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills),
MIT licensed, Copyright (c) 2025 K-Dense Inc.

- Adapted path: [`cloudra/skills/molecular-dynamics-simulation/`](../../cloudra/skills/molecular-dynamics-simulation/)
- Upstream skill: `skills/molecular-dynamics/`
- Upstream license: MIT

The upstream skill is written around OpenMM and MDAnalysis. Earlier Cloudra revisions
included examples derived from those implementations. The current guide documents
Cloudra's preparation and scheduling tools and includes native GROMACS examples.

The provenance was recorded in the skill's frontmatter when it was first adapted, but was
dropped during the skill rewrite in commit `27931d88` ("feat(skills): upgrade
first-principles, literature, docking, md, and subagent skills"). It was restored on
`metadata` in the skill frontmatter and recorded here.

**How to keep this from recurring:** when a skill is adapted from an upstream source, the
upstream project, upstream path, license and copyright line belong in the skill's
frontmatter `metadata` block, and the full upstream permission notice belongs in this
directory. Editing a skill's body must not drop that block.

The upstream MIT permission notice is preserved below.


MIT License

Copyright (c) 2025 K-Dense Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
