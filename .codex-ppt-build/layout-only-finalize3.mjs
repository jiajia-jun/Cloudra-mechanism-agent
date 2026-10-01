import {pathToFileURL} from 'node:url';
import fs from 'node:fs/promises';
const root='/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master';
const skill='/Users/cloudrayyy/.codex/plugins/cache/openai-primary-runtime/presentations/26.929.10730/skills/presentations';
const {finalizePresentation}=await import(pathToFileURL(skill+'/container_tools/artifact_tool_utils.mjs'));
const result=await finalizePresentation({workspaceDir:root,candidatePath:root+'/.codex-ppt-build/layout-only-candidate.pptx',finalPath:root+'/output/Cloudra_研发新范式版_仅排版修订_交付.pptx',pythonExecutable:'/Users/cloudrayyy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3',integrityValidatorPath:skill+'/container_tools/inspect_presentation_package_integrity.py',layoutValidatorPath:skill+'/container_tools/inspect_presentation_layout_geometry.py',layoutArgs:['--expected-slide-size-emu','12179300,6858000','--validate-bullet-geometry','--validate-heading-fit'],explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:[],requiredNativeChartOwnerSlides:[],fontPolicy:{basis:'design',families:['Hiragino Sans GB']},verifyArtifactToolImport:true,receiptPath:root+'/.codex-ppt-build/layout-only-delivery-validation.json'});
console.log(JSON.stringify(result,null,2));
