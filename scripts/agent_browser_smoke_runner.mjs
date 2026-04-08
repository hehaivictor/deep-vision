#!/usr/bin/env node

import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, join, normalize } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';


const __filename = fileURLToPath(import.meta.url);
const ROOT_DIR = normalize(join(dirname(__filename), '..'));
const WEB_DIR = join(ROOT_DIR, 'web');
const LIVE_AUTH_PHONE = '13800138000';
const LIVE_SMS_CODE = '666666';
const LIVE_UV_WITH_ARGS = [
  '--with',
  'flask',
  '--with',
  'flask-cors',
  '--with',
  'anthropic',
  '--with',
  'requests',
  '--with',
  'reportlab',
  '--with',
  'pillow',
  '--with',
  'jdcloud-sdk',
  '--with',
  'psycopg[binary]',
  '--with',
  'boto3',
];
const LIVE_REPORT_TITLE = '真实浏览器方案验证报告';
const LIVE_HELPER_SCRIPT = String.raw`#!/usr/bin/env python3
import argparse
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(os.environ["DEEPVISION_ROOT_DIR"]).resolve()
SERVER_PATH = ROOT_DIR / "web" / "server.py"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def load_server():
    spec = importlib.util.spec_from_file_location("dv_browser_live_helper", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载服务模块: {SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_report_content(title: str) -> str:
    return (
        f"# {title}\n\n"
        "## 一、需求摘要\n\n"
        "当前需要验证真实后端下的报告详情、方案页和公开分享边界。\n\n"
        "## 二、结论建议\n\n"
        "建议按回访入口、闭环时效和复盘节奏三条主线推进试点，并保留可公开分享的只读方案页。\n\n"
        "## 附录：完整访谈记录\n\n"
        "### 问题 1：这次真链路要验证什么？\n\n"
        "<div><strong>回答：</strong></div>\n"
        "<div>验证登录、License、报告详情、方案页和公开分享只读链路。</div>\n"
    )


def run_generate_license(args):
    server = load_server()
    payload = server.generate_license_batch(
        count=int(args.count),
        duration_days=int(args.duration_days),
        note=str(args.note or "").strip(),
        level_key=str(args.level_key or "professional").strip(),
        actor_user_id=None,
    )
    print(json.dumps(payload, ensure_ascii=False))


def run_seed_report(args):
    server = load_server()
    owner_user_id = int(args.owner_user_id)
    title = str(args.title or "").strip() or "真实浏览器方案验证报告"
    slug = server.normalize_topic_slug(title) or "browser-live-report"
    report_name = f"{slug}-{uuid.uuid4().hex[:8]}.md"
    report_path = server.REPORTS_DIR / report_name
    report_path.write_text(build_report_content(title), encoding="utf-8")
    server.set_report_owner_id(report_name, owner_user_id)
    payload = {
        "report_name": report_name,
        "title": title,
        "report_path": str(report_path),
    }
    print(json.dumps(payload, ensure_ascii=False))


def run_lookup_user(args):
    server = load_server()
    row = server.query_user_by_account(str(args.account or "").strip())
    if not row:
        print(json.dumps({"found": False, "account": str(args.account or "").strip()}, ensure_ascii=False))
        return
    print(json.dumps({
        "found": True,
        "user": {
            "id": int(row["id"]),
            "phone": str(row["phone"] or ""),
            "email": str(row["email"] or ""),
        },
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="DeepVision browser live helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_generate = subparsers.add_parser("generate-license")
    p_generate.add_argument("--count", type=int, default=1)
    p_generate.add_argument("--duration-days", type=int, default=30)
    p_generate.add_argument("--level-key", default="professional")
    p_generate.add_argument("--note", default="")
    p_generate.set_defaults(func=run_generate_license)

    p_seed = subparsers.add_parser("seed-report")
    p_seed.add_argument("--owner-user-id", required=True, type=int)
    p_seed.add_argument("--title", default="")
    p_seed.set_defaults(func=run_seed_report)

    p_lookup = subparsers.add_parser("lookup-user")
    p_lookup.add_argument("--account", required=True)
    p_lookup.set_defaults(func=run_lookup_user)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
`;

const MIME_TYPES = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

const args = process.argv.slice(2);
const suiteIndex = args.indexOf('--suite');
const suiteName = suiteIndex >= 0 ? String(args[suiteIndex + 1] || 'minimal').trim() || 'minimal' : 'minimal';

function nowIso() {
  return new Date().toISOString();
}

function buildSummary(results) {
  return results.reduce(
    (acc, item) => {
      const key = item.status === 'PASS' ? 'PASS' : item.status === 'WARN' ? 'WARN' : 'FAIL';
      acc[key] += 1;
      return acc;
    },
    { PASS: 0, WARN: 0, FAIL: 0 },
  );
}

function safeText(value, fallback = '') {
  const text = String(value ?? '').trim();
  return text || fallback;
}

function json(body) {
  return JSON.stringify(body);
}

function buildSolutionPayload() {
  return {
    report_name: 'demo-report.md',
    source_mode: 'degraded',
    title: '售后回访闭环试点方案',
    subtitle: '先围绕高频售后回访问题建立归因、分发和复盘闭环。',
    viewer_capabilities: { solution_share: true },
    hero: {
      eyebrow: '真实信息摘要',
      summary: '当前优先验证入口归因、分发动作和复盘节奏三件事。',
      metrics: [
        { label: '试点范围', value: '1 条业务线' },
        { label: '闭环节奏', value: '48h' },
        { label: '复盘周期', value: '每周' },
      ],
    },
    sections: [
      {
        id: 'why-now',
        label: '为什么现在做',
        title: '先把高信号反馈闭环跑通',
        description: '当前重复分发和漏处理已经影响试点判断。',
        layout: 'text',
        paragraphs: [
          '售后回访的核心问题不是数据不够，而是归因和分发不统一。',
          '先围绕一个业务线建立闭环，才能沉淀出可复制流程。',
        ],
      },
      {
        id: 'delivery',
        label: '落地路径',
        title: '按两阶段推进试点',
        description: '先验证入口与归因，再验证执行与复盘。',
        layout: 'timeline',
        items: [
          { title: '阶段一：锁定入口', summary: '统一回访问题标签与分发规则', detail: '第 1 周' },
          { title: '阶段二：闭环复盘', summary: '跟踪执行反馈并复盘处理质量', detail: '第 2 周' },
        ],
      },
    ],
  };
}

function buildReportsPayload() {
  return [
    {
      name: 'demo-report',
      title: '售后回访闭环试点报告',
      display_title: '售后回访闭环试点报告',
      scenario_name: '售后回访试点',
      created_at: '2026-04-01T08:00:00Z',
      session_id: 'session-demo-001',
      report_profile: 'balanced',
    },
  ];
}

function buildReportDetailPayload() {
  return {
    session_id: 'session-demo-001',
    title: '售后回访闭环试点报告',
    report_profile: 'balanced',
    report_variant_label: '普通版',
    source_report_name: '',
    content: [
      '# 售后回访闭环试点报告',
      '',
      '## 核心判断',
      '',
      '- 当前首要问题是回访归因与分发规则不统一。',
      '- 先围绕一个业务线验证闭环，再扩大到更多场景。',
      '',
      '## 下一步动作',
      '',
      '1. 对齐回访问题标签。',
      '2. 建立 48 小时闭环机制。',
    ].join('\n'),
  };
}

function buildStatusPayload() {
  return {
    authenticated: true,
    user: {
      id: 1,
      phone: '13800138000',
      account: 'admin',
      name: 'Admin',
      is_admin: true,
    },
    level: {
      key: 'professional',
      name: '专业版',
      description: '支持方案页与高级导出能力',
      sort_order: 30,
    },
    capabilities: {
      'report.generate': true,
      'report.profile.quality': true,
      'report.export.basic': true,
      'report.export.docx': true,
      'report.export.appendix': true,
      'solution.view': true,
      'solution.share': true,
      'presentation.generate': false,
      'interview.mode.quick': true,
      'interview.mode.standard': true,
      'interview.mode.deep': true,
    },
    allowed_report_profiles: ['balanced', 'quality'],
    report_profile_default: 'balanced',
    allowed_interview_modes: ['quick', 'standard', 'deep'],
    interview_mode_default: 'standard',
    has_valid_license: true,
    status: 'active',
    license_enforcement_enabled: true,
    license: {
      has_valid_license: true,
      status: 'active',
      license: {
        code: 'LIC-DEMO-001',
        level: 'professional',
      },
    },
    ai_available: false,
    sms_login_enabled: false,
    wechat_login_enabled: false,
  };
}

function buildLicenseCurrentPayload(statusPayload) {
  const statusLicensePayload = statusPayload?.license && typeof statusPayload.license === 'object'
    ? statusPayload.license
    : {};
  return {
    enforcement_enabled: Boolean(statusPayload?.license_enforcement_enabled),
    has_valid_license: Boolean(
      statusLicensePayload?.has_valid_license ?? statusPayload?.has_valid_license,
    ),
    status: safeText(statusLicensePayload?.status ?? statusPayload?.status, 'missing'),
    license: statusLicensePayload?.license ?? null,
  };
}

function buildConfigPayload() {
  return {
    meta: {
      restart_hint: '配置写入文件后通常需要重启服务。',
      source_meta: {
        env: { hint: '环境变量会写入 .env.local。' },
        config: { hint: '运行配置会写入 config.py。' },
        site: { hint: '前端共享配置会写入 site-config.js。' },
      },
    },
    env: {
      file: { path: '.env.local', exists: true },
      groups: [
        {
          id: 'ai',
          title: 'AI 配置',
          description: '模型与服务开关',
          items: [
            { key: 'MODEL_NAME', label: '模型名称', value: 'claude-sonnet-4', description: '默认模型' },
          ],
        },
      ],
    },
    config: {
      file: { path: 'config.py', exists: true },
      groups: [
        {
          id: 'runtime',
          title: '运行配置',
          description: '服务运行与调试开关',
          items: [
            { key: 'DEBUG_MODE', label: '调试模式', value: 'False', description: '生产关闭' },
          ],
        },
      ],
    },
    site: {
      file: { path: 'web/site-config.js', exists: true },
      groups: [
        {
          id: 'brand',
          title: '前端品牌',
          description: '站点标题与品牌文案',
          items: [
            { key: 'site_title', label: '站点标题', value: 'DeepVision', description: '默认标题' },
          ],
        },
      ],
    },
  };
}

async function startStaticServer() {
  const server = createServer(async (req, res) => {
    try {
      const incomingUrl = new URL(req.url || '/', 'http://127.0.0.1');
      let pathname = incomingUrl.pathname || '/';
      if (pathname === '/') pathname = '/index.html';
      const relativePath = normalize(pathname).replace(/^(\.\.(\/|\\|$))+/, '').replace(/^[/\\]+/, '');
      const filePath = join(WEB_DIR, relativePath);
      if (!filePath.startsWith(WEB_DIR)) {
        res.writeHead(403, { 'content-type': 'text/plain; charset=utf-8' });
        res.end('forbidden');
        return;
      }
      const body = await readFile(filePath);
      res.writeHead(200, { 'content-type': MIME_TYPES[extname(filePath)] || 'application/octet-stream' });
      res.end(body);
    } catch (error) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('not found');
    }
  });
  return await new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      resolve({
        server,
        baseUrl: `http://127.0.0.1:${address.port}`,
      });
    });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function reserveTcpPort() {
  const server = createServer(() => {});
  return await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolve(address?.port);
      });
    });
  });
}

function attachProcessLog(stream, target, prefix) {
  if (!stream) return;
  stream.setEncoding('utf8');
  stream.on('data', (chunk) => {
    for (const rawLine of String(chunk || '').split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line) continue;
      target.push(`${prefix}${line}`);
      if (target.length > 120) {
        target.splice(0, target.length - 120);
      }
    }
  });
}

function recentLines(lines, limit = 8) {
  return lines.slice(-limit);
}

function liveCommandEnv(context) {
  return {
    ...process.env,
    DEEPVISION_ROOT_DIR: ROOT_DIR,
    DEEPVISION_ENV_FILE: context.envFilePath,
    DEEPVISION_DATA_DIR: context.dataDir,
    PYTHONUNBUFFERED: '1',
  };
}

async function stopChildProcess(child, timeoutMs = 8000) {
  if (!child || child.exitCode !== null || child.signalCode) return;
  child.kill('SIGTERM');
  await Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    sleep(timeoutMs),
  ]);
  if (child.exitCode === null && !child.signalCode) {
    child.kill('SIGKILL');
    await new Promise((resolve) => child.once('exit', resolve));
  }
}

async function runCommand(command, args, options = {}) {
  const {
    cwd = ROOT_DIR,
    env = process.env,
    timeoutMs = 120000,
  } = options;
  return await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    let finished = false;
    const timer = setTimeout(() => {
      if (finished) return;
      finished = true;
      child.kill('SIGKILL');
      resolve({ code: 124, stdout, stderr: `${stderr}\ncommand timed out after ${timeoutMs}ms`.trim() });
    }, timeoutMs);

    child.stdout?.setEncoding('utf8');
    child.stderr?.setEncoding('utf8');
    child.stdout?.on('data', (chunk) => {
      stdout += String(chunk || '');
    });
    child.stderr?.on('data', (chunk) => {
      stderr += String(chunk || '');
    });
    child.once('error', (error) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      reject(error);
    });
    child.once('close', (code) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolve({ code: Number(code ?? 1), stdout, stderr });
    });
  });
}

async function ensureLiveHelperScript(context) {
  if (context.liveHelperPath) return context.liveHelperPath;
  const helperPath = join(context.runtimeRoot, 'agent_browser_live_helper.py');
  await writeFile(helperPath, LIVE_HELPER_SCRIPT, 'utf8');
  context.liveHelperPath = helperPath;
  return helperPath;
}

function parseCommandJson(result, label) {
  try {
    const rawStdout = String(result.stdout || '').trim();
    const jsonStart = rawStdout.indexOf('{');
    const jsonEnd = rawStdout.lastIndexOf('}');
    if (jsonStart < 0 || jsonEnd <= jsonStart) {
      throw new Error('stdout 中未找到 JSON 片段');
    }
    return JSON.parse(rawStdout.slice(jsonStart, jsonEnd + 1));
  } catch (error) {
    throw new Error(`解析 ${label} 输出失败: ${safeText(error?.message, String(error))}`);
  }
}

async function runLiveHelper(context, args, options = {}) {
  const helperPath = await ensureLiveHelperScript(context);
  return await runCommand(
    'uv',
    [
      'run',
      ...LIVE_UV_WITH_ARGS,
      'python3',
      helperPath,
      ...args,
    ],
    {
      cwd: ROOT_DIR,
      env: liveCommandEnv(context),
      timeoutMs: options.timeoutMs || 120000,
    },
  );
}

async function waitForServerReady(baseUrl, logs, timeoutMs = 45000) {
  const startedAt = Date.now();
  let lastError = '';
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(`${baseUrl}/api/status`);
      if (response.ok) {
        return;
      }
      lastError = `status=${response.status}`;
    } catch (error) {
      lastError = safeText(error?.message, String(error));
    }
    await sleep(500);
  }
  const logHint = recentLines(logs, 10).join('\n');
  throw new Error(
    [
      `真实后端启动超时: ${safeText(lastError, '未收到 /api/status 响应')}`,
      logHint,
    ].filter(Boolean).join('\n'),
  );
}

function buildLiveEnvFile(port) {
  return [
    'DEBUG_MODE=true',
    'ENABLE_AI=false',
    'ENABLE_DEBUG_LOG=false',
    'SUPPRESS_STATUS_POLL_ACCESS_LOG=true',
    'FOCUS_GENERATION_ACCESS_LOG=false',
    'SECRET_KEY=browser-live-secret',
    'INSTANCE_SCOPE_KEY=browser-live-instance',
    'SMS_PROVIDER=mock',
    `SMS_TEST_CODE=${LIVE_SMS_CODE}`,
    'LICENSE_ENFORCEMENT_ENABLED=true',
    'SERVER_HOST=127.0.0.1',
    `SERVER_PORT=${port}`,
  ].join('\n') + '\n';
}

async function generateLiveLicense(context) {
  const result = await runLiveHelper(
    context,
    [
      'generate-license',
      '--count',
      '1',
      '--duration-days',
      '30',
      '--level-key',
      'professional',
      '--note',
      'browser-live-smoke',
    ],
    { timeoutMs: 120000 },
  );

  if (result.code !== 0) {
    throw new Error(
      [
        '生成 live License 失败',
        safeText(result.stderr),
        safeText(result.stdout),
      ].filter(Boolean).join('\n'),
    );
  }

  const payload = parseCommandJson(result, 'live License');
  const licenseCode = safeText(payload?.licenses?.[0]?.code);
  if (!licenseCode) {
    throw new Error('live License 输出中缺少可用 code');
  }
  return licenseCode;
}

async function startLiveBackend() {
  const runtimeRoot = await mkdtemp(join(tmpdir(), 'deepvision-browser-live-'));
  const dataDir = join(runtimeRoot, 'data');
  const envFilePath = join(runtimeRoot, '.env.browser-live');
  const authDbPath = join(dataDir, 'auth', 'users.db');
  const licenseDbPath = join(dataDir, 'auth', 'licenses.db');
  const logs = [];
  await mkdir(join(dataDir, 'auth'), { recursive: true });

  const port = await reserveTcpPort();
  await writeFile(envFilePath, buildLiveEnvFile(port), 'utf8');

  const child = spawn('uv', ['run', 'web/server.py'], {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      DEEPVISION_ENV_FILE: envFilePath,
      DEEPVISION_DATA_DIR: dataDir,
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  attachProcessLog(child.stdout, logs, '[stdout] ');
  attachProcessLog(child.stderr, logs, '[stderr] ');

  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    await waitForServerReady(baseUrl, logs);
    const licenseCode = await generateLiveLicense({
      runtimeRoot,
      envFilePath,
      dataDir,
      authDbPath,
      licenseDbPath,
    });
    return {
      mode: 'live',
      baseUrl,
      runtimeRoot,
      dataDir,
      envFilePath,
      authDbPath,
      licenseDbPath,
      licenseCode,
      authPhone: LIVE_AUTH_PHONE,
      smsCode: LIVE_SMS_CODE,
      cleanup: async () => {
        await stopChildProcess(child);
        await rm(runtimeRoot, { recursive: true, force: true });
      },
    };
  } catch (error) {
    await stopChildProcess(child);
    await rm(runtimeRoot, { recursive: true, force: true });
    throw new Error(
      [
        safeText(error?.message, String(error)),
        ...recentLines(logs, 10),
      ].filter(Boolean).join('\n'),
    );
  }
}

function buildApiHandler(baseUrl, options = {}) {
  const solutionPayload = options.solutionPayload || buildSolutionPayload();
  const reportsPayload = options.reportsPayload || buildReportsPayload();
  const reportDetailPayload = options.reportDetailPayload || buildReportDetailPayload();
  const statusPayload = options.statusPayload || buildStatusPayload();
  const licenseCurrentPayload = options.licenseCurrentPayload || buildLicenseCurrentPayload(statusPayload);
  const licenseActivatePayload = options.licenseActivatePayload || null;
  const configPayload = buildConfigPayload();
  return async (route) => {
    const url = new URL(route.request().url());
    if (!url.href.startsWith(`${baseUrl}/api/`)) {
      await route.continue();
      return;
    }

    const { pathname, searchParams } = url;
    const method = route.request().method().toUpperCase();

    if (method === 'GET' && pathname === '/api/status') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json(statusPayload) });
      return;
    }
    if (method === 'GET' && pathname === '/api/licenses/current') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json(licenseCurrentPayload),
      });
      return;
    }
    if (method === 'POST' && pathname === '/api/licenses/activate' && licenseActivatePayload) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json(licenseActivatePayload),
      });
      return;
    }
    if (method === 'GET' && pathname === '/api/scenarios') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json([]) });
      return;
    }
    if (method === 'GET' && pathname === '/api/sessions') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json([]) });
      return;
    }
    if (method === 'GET' && pathname === '/api/reports') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json(reportsPayload) });
      return;
    }
    if (method === 'GET' && pathname === '/api/reports/demo-report') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json(reportDetailPayload) });
      return;
    }
    if (method === 'GET' && pathname === '/api/metrics') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json({ total: 12, last_n: Number(searchParams.get('last_n') || 200), failures: 0, items: [] }),
      });
      return;
    }
    if (method === 'GET' && pathname === '/api/summaries') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json({
          enabled: true,
          cache_enabled: true,
          cached_count: 0,
          cache_size_bytes: 0,
          threshold: 6,
          target_length: 800,
        }),
      });
      return;
    }
    if (method === 'GET' && pathname === '/api/admin/ownership-migrations') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json({ items: [] }) });
      return;
    }
    if (method === 'GET' && pathname === '/api/admin/licenses/summary') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json({
          totals: { active: 1, revoked: 0, expired: 0 },
          enforcement: { enabled: true, follow_default: false },
          presentation_feature: { enabled: true, follow_default: false },
        }),
      });
      return;
    }
    if (method === 'GET' && pathname === '/api/admin/config-center') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json(configPayload) });
      return;
    }
    if (method === 'GET' && pathname === '/api/reports/demo-report/solution') {
      await route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: json(solutionPayload) });
      return;
    }
    if (method === 'POST' && pathname === '/api/reports/demo-report/solution/share') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json({ share_url: `${baseUrl}/solution.html?share=demo-public-token` }),
      });
      return;
    }
    if (method === 'GET' && pathname === '/api/public/solutions/demo-public-token') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: json({
          ...solutionPayload,
          share_mode: 'public',
          report_name: '',
          viewer_capabilities: { solution_share: false },
        }),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: 'application/json; charset=utf-8',
      body: json({ error: `unmocked api: ${method} ${pathname}` }),
    });
  };
}

async function runWithPage(browser, baseUrl, initScript, callback, initArg = undefined, apiOptions = undefined, apiMode = 'mock', contextOptions = undefined) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1080 },
    ...(contextOptions || {}),
  });
  if (initScript) {
    await context.addInitScript(initScript, initArg);
  }
  const errors = [];
  const page = await context.newPage();
  page.on('pageerror', (error) => {
    errors.push(`pageerror: ${safeText(error?.message, String(error))}`);
  });
  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(`console.error: ${safeText(message.text())}`);
    }
  });
  if (apiMode === 'mock') {
    await page.route('**/api/**', buildApiHandler(baseUrl, apiOptions));
  }
  try {
    await callback(page);
    if (errors.length) {
      throw new Error(errors.slice(0, 6).join('\n'));
    }
  } finally {
    await context.close();
  }
}

async function fetchPageJson(page, path, options = {}) {
  return await page.evaluate(
    async ({ targetPath, requestOptions }) => {
      const response = await fetch(targetPath, {
        credentials: 'same-origin',
        ...requestOptions,
      });
      const text = await response.text();
      let payload = null;
      try {
        payload = JSON.parse(text);
      } catch (_error) {
        payload = null;
      }
      return {
        ok: response.ok,
        status: response.status,
        text,
        payload,
      };
    },
    {
      targetPath: path,
      requestOptions: options,
    },
  );
}

async function waitForLiveAppState(page, timeoutMs = 20000) {
  const stateHandle = await page.waitForFunction(() => {
    const isVisible = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      return !node.hidden
        && style.display !== 'none'
        && style.visibility !== 'hidden'
        && style.opacity !== '0'
        && node.getClientRects().length > 0;
    };
    const licenseInput = document.querySelector('#license-code-input');
    if (isVisible(licenseInput)) return 'license';
    const titleHit = Array.from(document.querySelectorAll('h2, h3')).some(
      (node) => isVisible(node) && String(node.textContent || '').includes('访谈会话'),
    );
    const primaryActionHit = Array.from(document.querySelectorAll('button')).some(
      (button) => isVisible(button) && String(button.textContent || '').includes('新建访谈'),
    );
    if (titleHit || primaryActionHit) return 'home';
    return '';
  }, { timeout: timeoutMs });
  return safeText(await stateHandle.jsonValue(), 'unknown');
}

async function waitForLiveHomeReady(page, timeoutMs = 25000) {
  await page.waitForFunction(() => {
    const isVisible = (node) => {
      if (!(node instanceof HTMLElement)) return false;
      const style = window.getComputedStyle(node);
      return !node.hidden
        && style.display !== 'none'
        && style.visibility !== 'hidden'
        && style.opacity !== '0'
        && node.getClientRects().length > 0;
    };
    const titleHit = Array.from(document.querySelectorAll('h2, h3')).some(
      (node) => isVisible(node) && String(node.textContent || '').includes('访谈会话'),
    );
    const primaryActionHit = Array.from(document.querySelectorAll('button')).some((button) => {
      const text = String(button.textContent || '');
      return isVisible(button) && (text.includes('新建访谈') || text.includes('报告'));
    });
    const gateVisible = isVisible(document.querySelector('#license-code-input'));
    return (titleHit || primaryActionHit) && !gateVisible;
  }, { timeout: timeoutMs });
}

async function performLiveLoginAndLicense(page, baseUrl, liveContext) {
  await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
  let initialState = '';
  try {
    initialState = await waitForLiveAppState(page, 5000);
  } catch (_error) {
    initialState = '';
  }

  if (initialState === 'home') {
    await waitForLiveHomeReady(page, 10000);
    liveContext.storageState = await page.context().storageState();
    return await lookupLiveUserRecord(liveContext);
  }

  if (initialState === 'license') {
    const activateResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/api/licenses/activate') && response.request().method() === 'POST',
      { timeout: 20000 },
    );
    await page.fill('#license-code-input', liveContext.licenseCode);
    await page.getByRole('button', { name: '绑定 License', exact: true }).click({ timeout: 20000 });
    const activateResponse = await activateResponsePromise;
    if (!activateResponse.ok()) {
      throw new Error(`License 绑定失败: status=${activateResponse.status()}`);
    }
    await waitForLiveHomeReady(page, 25000);
    liveContext.storageState = await page.context().storageState();
    return await lookupLiveUserRecord(liveContext);
  }

  await page.waitForSelector('#auth-account', { timeout: 20000 });
  await page.fill('#auth-account', liveContext.authPhone);
  await page.waitForFunction(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const target = buttons.find((button) => String(button.textContent || '').includes('获取验证码'));
    return Boolean(target && !target.disabled);
  }, { timeout: 20000 });
  await page.locator('button:visible').filter({ hasText: '获取验证码' }).first().click({ timeout: 20000 });
  await page.waitForFunction(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.some((button) => /后重发|发送中/.test(String(button.textContent || '')));
  }, { timeout: 15000 });

  await page.fill('#auth-code', liveContext.smsCode);
  await page.waitForFunction(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const target = buttons.find((button) => String(button.textContent || '').trim() === '登录');
    return Boolean(target && !target.disabled);
  }, { timeout: 20000 });
  const loginResponsePromise = page.waitForResponse(
    (response) => response.url().includes('/api/auth/login/code') && response.request().method() === 'POST',
    { timeout: 20000 },
  );
  await page.getByRole('button', { name: '登录', exact: true }).click({ timeout: 20000 });
  const loginResponse = await loginResponsePromise;
  if (!loginResponse.ok()) {
    throw new Error(`验证码登录失败: status=${loginResponse.status()}`);
  }

  let nextState = 'unknown';
  try {
    nextState = await waitForLiveAppState(page, 20000);
  } catch (_error) {
    await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
    try {
      nextState = await waitForLiveAppState(page, 10000);
    } catch (retryError) {
      throw new Error(`登录后未进入预期状态: ${safeText(retryError?.message, String(retryError))}`);
    }
  }

  if (nextState === 'license') {
    const activateResponsePromise = page.waitForResponse(
      (response) => response.url().includes('/api/licenses/activate') && response.request().method() === 'POST',
      { timeout: 20000 },
    );
    await page.fill('#license-code-input', liveContext.licenseCode);
    await page.getByRole('button', { name: '绑定 License', exact: true }).click({ timeout: 20000 });
    const activateResponse = await activateResponsePromise;
    if (!activateResponse.ok()) {
      throw new Error(`License 绑定失败: status=${activateResponse.status()}`);
    }
  }

  try {
    await waitForLiveHomeReady(page, 25000);
  } catch (_error) {
    await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
    await waitForLiveHomeReady(page, 12000);
  }
  liveContext.storageState = await page.context().storageState();
  return await lookupLiveUserRecord(liveContext);
}

async function ensureLiveReportFixture(page, liveContext) {
  if (liveContext.reportFixture) {
    return liveContext.reportFixture;
  }
  let currentUser = liveContext.userRecord || null;
  if (!currentUser?.id) {
    await performLiveLoginAndLicense(page, liveContext.baseUrl, liveContext);
    currentUser = await lookupLiveUserRecord(liveContext);
  }
  const result = await runLiveHelper(
    liveContext,
    [
      'seed-report',
      '--owner-user-id',
      String(currentUser.id),
      '--title',
      LIVE_REPORT_TITLE,
    ],
    { timeoutMs: 120000 },
  );
  if (result.code !== 0) {
    throw new Error(
      [
        'seed live report 失败',
        safeText(result.stderr),
        safeText(result.stdout),
      ].filter(Boolean).join('\n'),
    );
  }
  const payload = parseCommandJson(result, 'live report fixture');
  const reportName = safeText(payload?.report_name);
  if (!reportName) {
    throw new Error('live report fixture 缺少 report_name');
  }
  liveContext.reportFixture = {
    report_name: reportName,
    title: safeText(payload?.title, LIVE_REPORT_TITLE),
    report_path: safeText(payload?.report_path),
  };
  return liveContext.reportFixture;
}

async function lookupLiveUserRecord(liveContext) {
  if (liveContext.userRecord?.id) {
    return liveContext.userRecord;
  }
  const result = await runLiveHelper(
    liveContext,
    [
      'lookup-user',
      '--account',
      liveContext.authPhone,
    ],
    { timeoutMs: 60000 },
  );
  if (result.code !== 0) {
    throw new Error(
      [
        '查询 live 用户失败',
        safeText(result.stderr),
        safeText(result.stdout),
      ].filter(Boolean).join('\n'),
    );
  }
  const payload = parseCommandJson(result, 'live user lookup');
  if (!payload?.found || !payload?.user?.id) {
    throw new Error(`未找到 live 用户: ${liveContext.authPhone}`);
  }
  liveContext.userRecord = payload.user;
  return liveContext.userRecord;
}

async function scenarioHelpDocs(browser, baseUrl) {
  await runWithPage(browser, baseUrl, null, async (page) => {
    await page.goto(`${baseUrl}/help.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('text=帮助文档', { timeout: 10000 });
    const title = await page.title();
    if (!title.includes('帮助文档')) {
      throw new Error(`帮助页标题异常: ${title}`);
    }
  });
  return '标题与帮助文档主文案可见';
}

async function scenarioSolutionShare(browser, baseUrl) {
  await runWithPage(browser, baseUrl, null, async (page) => {
    await page.goto(`${baseUrl}/solution.html?report=demo-report`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#solution-shell:not([hidden])', { timeout: 10000 });
    await page.waitForSelector('#btn-share', { timeout: 10000 });
    await page.click('#btn-share');
    await page.waitForSelector('#solution-share-panel:not([hidden])', { timeout: 10000 });
    const shareValue = await page.inputValue('#solution-share-input');
    if (!shareValue.includes('share=demo-public-token')) {
      throw new Error(`分享链接异常: ${shareValue}`);
    }
  });
  return '方案页成功渲染，分享面板可打开并写入匿名只读链接';
}

async function scenarioAdminConfigEntry(browser, baseUrl) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
      await page.locator('button:has-text("管理员中心")').first().click({ timeout: 15000 });
      await page.waitForSelector('h2:has-text("管理员中心")', { timeout: 15000 });
    },
  );
  return '管理员账号可从主界面进入管理员中心';
}

async function scenarioSolutionPublicReadonly(browser, baseUrl) {
  await runWithPage(browser, baseUrl, null, async (page) => {
    await page.goto(`${baseUrl}/solution.html?share=demo-public-token`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#solution-shell:not([hidden])', { timeout: 10000 });
    await page.waitForSelector('text=外部分享 · 只读方案', { timeout: 10000 });
    const actionBarHidden = await page.locator('#solution-action-bar').evaluate((element) => element.hidden);
    if (!actionBarHidden) {
      throw new Error('公开分享模式下不应显示分享动作栏');
    }
    const shareButtonCount = await page.locator('#btn-share:visible').count();
    if (shareButtonCount > 0) {
      throw new Error('公开分享模式下不应暴露分享按钮');
    }
  });
  return '公开分享模式可渲染，并保持只读边界';
}

async function scenarioLoginView(browser, baseUrl) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('h2:has-text("欢迎回来")', { timeout: 15000 });
      await page.waitForSelector('text=登录后即可使用访谈与报告功能', { timeout: 15000 });
      await page.waitForSelector('text=当前未启用可用登录方式，请联系管理员。', { timeout: 15000 });
      if (await page.locator('#auth-account').isVisible()) {
        throw new Error('短信登录关闭时，不应展示手机号输入框');
      }
      if (await page.locator('#auth-code').isVisible()) {
        throw new Error('短信登录关闭时，不应展示验证码输入框');
      }
      const loginButton = page.getByRole('button', { name: '登录', exact: true });
      if (await loginButton.isVisible()) {
        throw new Error('短信登录关闭时，不应展示短信登录按钮');
      }
      const licenseGateVisible = await page.locator('h2:has-text("请输入 License 继续使用")').count();
      if (licenseGateVisible > 0) {
        throw new Error('未登录状态不应直接进入 License gate');
      }
    },
    undefined,
    {
      statusPayload: {
        ...buildStatusPayload(),
        authenticated: false,
        user: null,
        has_valid_license: false,
        status: 'missing',
        license: null,
        sms_login_enabled: false,
        wechat_login_enabled: false,
      },
      licenseCurrentPayload: {
        enforcement_enabled: true,
        has_valid_license: false,
        status: 'missing',
        license: null,
      },
    },
  );
  return '未登录状态会隐藏短信登录表单，并提示当前未启用可用登录方式';
}

async function scenarioLicenseGateView(browser, baseUrl) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('h2:has-text("请输入 License 继续使用")', { timeout: 15000 });
      await page.waitForSelector('text=登录后必须绑定有效 License，才能继续使用访谈与报告功能。', { timeout: 15000 });
      await page.waitForSelector('#license-code-input', { timeout: 15000 });
      await page.getByRole('button', { name: '绑定 License', exact: true }).waitFor({ timeout: 15000 });
      await page.getByRole('button', { name: '退出登录', exact: true }).waitFor({ timeout: 15000 });
      const primaryNavVisible = await page.locator('button:visible').filter({ hasText: '新建访谈' }).count();
      if (primaryNavVisible > 0) {
        throw new Error('License gate 生效时不应显示主业务导航');
      }
    },
    undefined,
    {
      statusPayload: {
        ...buildStatusPayload(),
        has_valid_license: false,
        status: 'missing',
        license: {
          has_valid_license: false,
          status: 'missing',
          license: null,
        },
      },
      licenseCurrentPayload: {
        enforcement_enabled: true,
        has_valid_license: false,
        status: 'missing',
        license: null,
      },
    },
  );
  return '已登录但无有效 License 时，会展示 License gate 与绑定入口';
}

async function scenarioLicenseActivateSuccess(browser, baseUrl) {
  const activatedPayload = {
    enforcement_enabled: true,
    has_valid_license: true,
    status: 'active',
    license: {
      code: 'LIC-ACTIVATED-001',
      masked_code: 'LIC-****-0001',
      level: 'professional',
      expires_at: '2030-12-31T00:00:00Z',
      not_before_at: '2026-01-01T00:00:00Z',
    },
    message: 'License 绑定成功',
  };
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('#license-code-input', { timeout: 15000 });
      await page.fill('#license-code-input', 'LIC-ACTIVATED-001');
      await page.getByRole('button', { name: '绑定 License', exact: true }).click({ timeout: 15000 });
      await page.waitForSelector('h2:has-text("访谈会话")', { timeout: 15000 });
      await page.locator('button:visible').filter({ hasText: '新建访谈' }).first().waitFor({ timeout: 15000 });
      const gateStillVisible = await page.locator('h2:has-text("请输入 License 继续使用")').count();
      if (gateStillVisible > 0) {
        throw new Error('License 绑定成功后不应继续停留在 License gate');
      }
    },
    undefined,
    {
      statusPayload: {
        ...buildStatusPayload(),
        has_valid_license: false,
        status: 'missing',
        license: {
          has_valid_license: false,
          status: 'missing',
          license: null,
        },
      },
      licenseCurrentPayload: {
        enforcement_enabled: true,
        has_valid_license: false,
        status: 'missing',
        license: null,
      },
      licenseActivatePayload: activatedPayload,
    },
  );
  return 'License 绑定成功后会退出门禁，并回到访谈会话主页';
}

async function scenarioReportDetailFlow(browser, baseUrl) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
      await page.getByRole('button', { name: '报告', exact: true }).click({ timeout: 15000 });
      await page.waitForSelector('[data-report-key="demo-report"]', { timeout: 15000 });
      await page.locator('[data-report-key="demo-report"]').click({ timeout: 15000 });
      await page.waitForSelector('.dv-report-title', { timeout: 15000 });
      const titleText = await page.locator('.dv-report-title').first().textContent();
      if (!safeText(titleText).includes('售后回访闭环试点报告')) {
        throw new Error(`报告详情标题异常: ${safeText(titleText, '<empty>')}`);
      }
      await page.waitForSelector('text=核心判断', { timeout: 15000 });
      await page.getByRole('button', { name: '查看方案', exact: true }).waitFor({ timeout: 15000 });
      await page.getByRole('button', { name: '返回报告列表', exact: true }).waitFor({ timeout: 15000 });
    },
  );
  return '可从报告列表进入报告详情，并看到方案入口按钮与核心报告内容';
}

async function scenarioAdminConfigTab(browser, baseUrl) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await page.goto(`${baseUrl}/index.html`, { waitUntil: 'domcontentloaded' });
      await page.locator('button:has-text("管理员中心")').first().click({ timeout: 15000 });
      await page.locator('button:has-text("配置中心")').first().click({ timeout: 15000 });
      await page.waitForSelector('h3:has-text("配置中心")', { timeout: 15000 });
      await page.waitForSelector('text=AI 配置', { timeout: 15000 });
      await page.getByRole('button', { name: 'config.py', exact: true }).click({ timeout: 15000 });
      await page.waitForSelector('text=运行配置', { timeout: 15000 });
      await page.getByRole('button', { name: '前端配置', exact: true }).click({ timeout: 15000 });
      await page.waitForSelector('text=前端品牌', { timeout: 15000 });
    },
  );
  return '配置中心可加载，并能在 env/config/site 三类来源间切换';
}

async function scenarioLiveLoginLicenseFlow(browser, baseUrl, liveContext) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await performLiveLoginAndLicense(page, baseUrl, liveContext);
      const gateVisible = await page.locator('h2:has-text("请输入 License 继续使用")').count();
      if (gateVisible > 0) {
        throw new Error('live 链路绑定 License 后仍停留在门禁页');
      }
    },
    undefined,
    undefined,
    'live',
    liveContext.storageState ? { storageState: liveContext.storageState } : undefined,
  );
  return `真实后端下已完成验证码登录与 License 绑定，手机号=${liveContext.authPhone}`;
}

async function scenarioLiveReportSolutionFlow(browser, baseUrl, liveContext) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await performLiveLoginAndLicense(page, baseUrl, liveContext);
      const fixture = await ensureLiveReportFixture(page, liveContext);

      await page.getByRole('button', { name: '报告', exact: true }).click({ timeout: 20000 });
      const reportSelector = `[data-report-key="${fixture.report_name}"]`;
      await page.waitForSelector(reportSelector, { timeout: 25000 });
      await page.locator(reportSelector).click({ timeout: 15000 });
      await page.waitForSelector('.dv-report-title', { timeout: 20000 });
      const titleText = safeText(await page.locator('.dv-report-title').first().textContent());
      if (!titleText.includes(fixture.title)) {
        throw new Error(`真实报告详情标题异常: ${titleText || '<empty>'}`);
      }

      const popupPromise = page.waitForEvent('popup');
      await page.getByRole('button', { name: '查看方案', exact: true }).click({ timeout: 15000 });
      const popup = await popupPromise;
      try {
        await popup.waitForLoadState('domcontentloaded');
        const solutionResponse = await popup.waitForResponse(
          (response) => response.ok() && response.url().includes(`/api/reports/${encodeURIComponent(fixture.report_name)}/solution`),
          { timeout: 25000 },
        );
        const payload = await solutionResponse.json();
        if (safeText(payload?.report_name) !== fixture.report_name) {
          throw new Error(`真实方案页 report_name 异常: ${safeText(payload?.report_name, '<empty>')}`);
        }
        await popup.waitForSelector('#solution-shell:not([hidden])', { timeout: 25000 });
        await popup.waitForSelector('#btn-share', { timeout: 25000 });
      } finally {
        await popup.close();
      }
    },
    undefined,
    undefined,
    'live',
    liveContext.storageState ? { storageState: liveContext.storageState } : undefined,
  );
  return '真实后端下已完成报告详情打开与方案页跳转';
}

async function scenarioLiveSolutionPublicShareFlow(browser, baseUrl, liveContext) {
  await runWithPage(
    browser,
    baseUrl,
    () => {
      localStorage.setItem('deepvision_intro_seen', 'true');
    },
    async (page) => {
      await performLiveLoginAndLicense(page, baseUrl, liveContext);
      const fixture = await ensureLiveReportFixture(page, liveContext);
      const shareTargetUrl = `${baseUrl}/solution.html?report=${encodeURIComponent(fixture.report_name)}`;
      await page.goto(shareTargetUrl, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('#solution-shell:not([hidden])', { timeout: 25000 });

      const shareResponsePromise = page.waitForResponse(
        (response) => response.ok()
          && response.request().method() === 'POST'
          && response.url().includes(`/api/reports/${encodeURIComponent(fixture.report_name)}/solution/share`),
        { timeout: 25000 },
      );
      await page.click('#btn-share', { timeout: 15000 });
      await page.waitForSelector('#solution-share-panel:not([hidden])', { timeout: 15000 });
      const shareInput = safeText(await page.inputValue('#solution-share-input'));
      const shareResponse = await shareResponsePromise;
      const sharePayload = await shareResponse.json();
      const shareUrl = safeText(sharePayload?.share_url || shareInput);
      if (!shareUrl.includes('share=')) {
        throw new Error(`真实分享链接异常: ${shareUrl || '<empty>'}`);
      }

      const browserRef = page.context().browser();
      if (!browserRef) {
        throw new Error('无法创建匿名浏览器上下文');
      }
      const anonymousContext = await browserRef.newContext({ viewport: { width: 1440, height: 1080 } });
      const publicPage = await anonymousContext.newPage();
      try {
        await publicPage.goto(shareUrl, { waitUntil: 'domcontentloaded' });
        await publicPage.waitForSelector('#solution-shell:not([hidden])', { timeout: 25000 });
        await publicPage.waitForSelector('text=外部分享 · 只读方案', { timeout: 25000 });
        const actionBarHidden = await publicPage.locator('#solution-action-bar').evaluate((element) => element.hidden);
        if (!actionBarHidden) {
          throw new Error('真实公开分享模式下不应显示分享动作栏');
        }
        const shareButtonCount = await publicPage.locator('#btn-share:visible').count();
        if (shareButtonCount > 0) {
          throw new Error('真实公开分享模式下不应暴露分享按钮');
        }
      } finally {
        await anonymousContext.close();
      }
    },
    undefined,
    undefined,
    'live',
    liveContext.storageState ? { storageState: liveContext.storageState } : undefined,
  );
  return '真实后端下已完成方案分享创建，并以匿名态访问只读公开分享页';
}

async function executeScenario(browser, baseUrl, scenario, runtimeContext = {}) {
  const startedAt = Date.now();
  try {
    let detail = '';
    if (scenario.id === 'help-docs') {
      detail = await scenarioHelpDocs(browser, baseUrl);
    } else if (scenario.id === 'solution-share') {
      detail = await scenarioSolutionShare(browser, baseUrl);
    } else if (scenario.id === 'admin-config-entry') {
      detail = await scenarioAdminConfigEntry(browser, baseUrl);
    } else if (scenario.id === 'solution-public-readonly') {
      detail = await scenarioSolutionPublicReadonly(browser, baseUrl);
    } else if (scenario.id === 'login-view') {
      detail = await scenarioLoginView(browser, baseUrl);
    } else if (scenario.id === 'license-gate-view') {
      detail = await scenarioLicenseGateView(browser, baseUrl);
    } else if (scenario.id === 'license-activate-success') {
      detail = await scenarioLicenseActivateSuccess(browser, baseUrl);
    } else if (scenario.id === 'report-detail-flow') {
      detail = await scenarioReportDetailFlow(browser, baseUrl);
    } else if (scenario.id === 'admin-config-tab') {
      detail = await scenarioAdminConfigTab(browser, baseUrl);
    } else if (scenario.id === 'live-login-license-flow') {
      detail = await scenarioLiveLoginLicenseFlow(browser, baseUrl, runtimeContext);
    } else if (scenario.id === 'live-report-solution-flow') {
      detail = await scenarioLiveReportSolutionFlow(browser, baseUrl, runtimeContext);
    } else if (scenario.id === 'live-solution-public-share-flow') {
      detail = await scenarioLiveSolutionPublicShareFlow(browser, baseUrl, runtimeContext);
    } else {
      throw new Error(`未知场景: ${scenario.id}`);
    }
    return {
      scenario_id: scenario.id,
      label: scenario.label,
      status: 'PASS',
      detail,
      duration_ms: Date.now() - startedAt,
      highlights: [],
    };
  } catch (error) {
    return {
      scenario_id: scenario.id,
      label: scenario.label,
      status: 'FAIL',
      detail: safeText(error?.message, 'browser smoke failed'),
      duration_ms: Date.now() - startedAt,
      highlights: [safeText(error?.stack, safeText(error?.message, 'browser smoke failed')).split('\n')[0]],
    };
  }
}

function resolveSuite(name) {
  if (name === 'minimal') {
    return {
      name: 'minimal',
      mode: 'mock',
      description: '帮助页 + 方案页分享 + 管理后台配置入口',
      scenarios: [
        { id: 'help-docs', label: '帮助文档静态页' },
        { id: 'solution-share', label: '方案页分享面板' },
        { id: 'admin-config-entry', label: '管理员中心入口' },
      ],
    };
  }
  if (name === 'extended') {
    return {
      name: 'extended',
      mode: 'mock',
      description: '在 minimal 基础上补公开分享只读、登录视图、License 门禁前端视图、License 绑定成功切换、报告详情链路与配置中心页签切换',
      scenarios: [
        { id: 'help-docs', label: '帮助文档静态页' },
        { id: 'solution-share', label: '方案页分享面板' },
        { id: 'admin-config-entry', label: '管理员中心入口' },
        { id: 'solution-public-readonly', label: '方案页公开分享只读' },
        { id: 'login-view', label: '登录前端视图' },
        { id: 'license-gate-view', label: 'License 门禁前端视图' },
        { id: 'license-activate-success', label: 'License 绑定成功后切回业务壳' },
        { id: 'report-detail-flow', label: '报告详情与方案入口' },
        { id: 'admin-config-tab', label: '管理员配置中心页签' },
      ],
    };
  }
  if (name === 'live-minimal') {
    return {
      name: 'live-minimal',
      mode: 'live',
      description: '隔离数据目录下启动真实后端，执行验证码登录与 License 绑定真链路',
      scenarios: [
        { id: 'live-login-license-flow', label: '真实后端登录与 License 绑定' },
      ],
    };
  }
  if (name === 'live-extended') {
    return {
      name: 'live-extended',
      mode: 'live',
      description: '在 live-minimal 基础上补真实报告详情、真实方案页和公开分享只读链路',
      scenarios: [
        { id: 'live-login-license-flow', label: '真实后端登录与 License 绑定' },
        { id: 'live-report-solution-flow', label: '真实后端报告详情与方案页' },
        { id: 'live-solution-public-share-flow', label: '真实后端公开分享只读链路' },
      ],
    };
  }
  if (name !== 'minimal') {
    throw new Error(`未知 browser smoke suite: ${name}`);
  }
}

async function main() {
  const suite = resolveSuite(suiteName);
  let runtime = null;
  const browser = await chromium.launch({ headless: true });
  try {
    runtime = suite.mode === 'live'
      ? await startLiveBackend()
      : await (async () => {
        const { server, baseUrl } = await startStaticServer();
        return {
          mode: 'mock',
          baseUrl,
          cleanup: async () => {
            await new Promise((resolve) => server.close(resolve));
          },
        };
      })();

    const results = [];
    for (const scenario of suite.scenarios) {
      results.push(await executeScenario(browser, runtime.baseUrl, scenario, runtime));
    }
    const summary = buildSummary(results);
    const payload = {
      generated_at: nowIso(),
      suite: suite.name,
      description: suite.description,
      mode: suite.mode,
      base_url: runtime.baseUrl,
      summary,
      overall: summary.FAIL > 0 ? 'BLOCKED' : 'READY',
      results,
    };
    if (suite.mode === 'live') {
      payload.runtime = {
        auth_phone: runtime.authPhone,
        auth_db_path: runtime.authDbPath,
        license_db_path: runtime.licenseDbPath,
      };
    }
    console.log(JSON.stringify(payload, null, 2));
    process.exit(summary.FAIL > 0 ? 2 : 0);
  } finally {
    await browser.close();
    if (runtime?.cleanup) {
      await runtime.cleanup();
    }
  }
}

main().catch((error) => {
  const payload = {
    generated_at: nowIso(),
    suite: suiteName,
    summary: { PASS: 0, WARN: 0, FAIL: 1 },
    overall: 'BLOCKED',
    results: [
      {
        scenario_id: 'runner',
        label: '浏览器 runner',
        status: 'FAIL',
        detail: safeText(error?.message, 'browser runner failed'),
        highlights: [safeText(error?.stack, safeText(error?.message, 'browser runner failed')).split('\n')[0]],
      },
    ],
  };
  console.log(JSON.stringify(payload, null, 2));
  process.exit(2);
});
