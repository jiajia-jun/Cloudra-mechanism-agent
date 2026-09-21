// 前端测试 runner：枚举 src/*.test.ts 逐个在子进程里执行。
//
// 存在的理由：这些 .test.ts 是「无框架脚本」（顶部 import node:assert，
// 失败即抛异常、退出码非零），node 无法一次喂多个文件，而把文件名写死在
// npm script 里已经在本次合并里出过事——清单里少了两个文件（新增的
// eventWindow/runtimeUrl）却照样报告"通过"。清单从目录读，增删文件自动生效。
import { spawnSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const files = readdirSync(join(frontendDir, 'src'))
  .filter((name) => name.endsWith('.test.ts'))
  .sort();

// 空清单一律失败：否则删光测试后 CI 会报"绿"。
if (files.length === 0) {
  console.error('no src/*.test.ts found — refusing to report success');
  process.exit(1);
}

const failed = [];
for (const file of files) {
  const result = spawnSync(
    process.execPath,
    ['--experimental-strip-types', join('src', file)],
    { cwd: frontendDir, stdio: 'inherit' },
  );
  if (result.status !== 0) failed.push(file);
}

const passed = files.length - failed.length;
console.log(`\nfrontend tests: ${passed}/${files.length} passed`);
if (failed.length > 0) {
  console.error(`failed: ${failed.join(', ')}`);
  process.exit(1);
}
