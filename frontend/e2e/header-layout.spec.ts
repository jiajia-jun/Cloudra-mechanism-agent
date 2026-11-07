import { expect, test, type Page } from '@playwright/test';
import { AGENT, PROJECT_ACTIVE, installApiMocks, openSpa } from './fixtures';

async function expectHeaderLayout(page: Page) {
  const problems = await page.locator('.agentbar').evaluate((header) => {
    const bounds = header.getBoundingClientRect();
    const visible = (selector: string) => [...header.querySelectorAll<HTMLElement>(selector)]
      .filter((element) => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden')
      .map((element) => ({ name: element.className, box: element.getBoundingClientRect(), element }));
    const groups = visible('.agentbar-left, .view-mode-switcher, .system-controls');
    const widgets = visible('.breadcrumb-project, .breadcrumb-agent-name, .breadcrumb-agent-select, .role-badge, .breadcrumb-current-task, .completion-badge');
    const controls = visible('button, select, .conn-status');
    const errors: string[] = [];
    for (const { name, box, element } of [...groups, ...widgets, ...controls]) {
      if (box.width <= 0 || box.height <= 0 || box.left < bounds.left - 1 || box.right > bounds.right + 1 || box.top < bounds.top - 1 || box.bottom > bounds.bottom + 1) {
        errors.push(`${name} leaves the header or has no usable size`);
      }
      if (element.tagName === 'SELECT' && box.width < 40) errors.push(`${name} is too narrow to use`);
      for (let parent = element.parentElement; parent && parent !== header; parent = parent.parentElement) {
        const style = getComputedStyle(parent), clip = parent.getBoundingClientRect();
        if (style.overflowX !== 'visible' && (box.left < clip.left - 1 || box.right > clip.right + 1)) errors.push(`${name} is clipped horizontally`);
        if (style.overflowY !== 'visible' && (box.top < clip.top - 1 || box.bottom > clip.bottom + 1)) errors.push(`${name} is clipped vertically`);
      }
    }
    const disjoint = (items: typeof groups) => {
      for (let first = 0; first < items.length; first++) {
        for (let second = first + 1; second < items.length; second++) {
          const a = items[first], b = items[second];
          if (Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left) > 1 && Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top) > 1) {
            errors.push(`${a.name} overlaps ${b.name}`);
          }
        }
      }
    };
    disjoint(groups);
    disjoint([...widgets, ...groups.filter(({ name }) => name !== 'agentbar-left')]);
    return errors;
  });
  expect(problems).toEqual([]);
}

for (const appearance of ['acid', 'punk', 'modernism']) {
  for (const multipleAgents of [false, true]) {
    test(`${appearance} header keeps ${multipleAgents ? 'multiple agents' : 'a single agent'} and controls apart`, async ({ page }) => {
      await page.setViewportSize({ width: 1400, height: 900 });
      await page.addInitScript((style) => {
        localStorage.setItem('cloudra.appearance', style);
        localStorage.setItem('cloudra:lang', 'zh');
        localStorage.setItem('cloudra:sidebar-open', 'true');
      }, appearance);
      const project = { ...PROJECT_ACTIVE, name: '机理探索工作台：长项目名称与计算证据核对 Long project name' };
      const agent = {
        ...AGENT,
        display_name: '反应机理研究协调员 Long coordinator name',
        current_task: '核对当前反应路径的结构、计算与证据关联，保留详细的研究任务说明 Long current task',
        completion: { run_id: 'run_header', run_outcome: 'succeeded', completion_basis: 'scope_completed', verification_label: 'scope_completed' },
      };
      const agents = multipleAgents ? [agent, { ...agent, id: 'agent_other', display_name: '另一位研究员' }] : [agent];
      await installApiMocks(page, { projects: [project], agents });
      await openSpa(page);
      await page.getByTitle(`选择项目: ${project.name}`, { exact: true }).click();
      await expect(page.locator('.agentbar .completion-badge')).toHaveText('scope completed');
      for (const width of [1400, 1024, 760]) {
        await page.setViewportSize({ width, height: 900 });
        for (const lang of ['zh', 'en']) {
          await page.locator('.lang-pill-btn').filter({ hasText: lang === 'zh' ? '中' : 'EN' }).click();
          for (const mode of ['dialogue', 'console']) {
            await page.locator('.view-mode-btn').nth(mode === 'dialogue' ? 0 : 1).click();
            await expectHeaderLayout(page);
          }
        }
      }
    });
  }
}
