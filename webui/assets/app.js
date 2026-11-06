/* TwitchDropsMiner web add-on.
 *
 * Vanilla ES2020, no build step. The page is served by the miner itself, so
 * every request is same-origin and the API token stays in localStorage (or
 * sessionStorage when "remember" is off).
 */
'use strict';

const TOKEN_KEY = 'tdm-api-token';
const TOKEN_SESSION_KEY = 'tdm-api-token-session';
const LANG_KEY = 'tdm-ui-lang';
const THEME_KEY = 'tdm-ui-theme';

const I18N = {
  en: {
    gate_hint: 'Enter the management token shown by api token in the miner\'s console.',
    token_placeholder: 'API token',
    remember: 'Remember on this browser',
    connect: 'Connect',
    connecting: 'Connecting…',
    invalid_token: 'That token was not accepted.',
    connection_failed: 'Could not reach the miner.',
    disconnect: 'Disconnect',
    tab_overview: 'Overview',
    tab_inventory: 'Drops inventory',
    tab_channels: 'Channels',
    tab_campaigns: 'Campaigns',
    tab_settings: 'Settings',
    tab_logs: 'Logs',
    engine: 'Engine',
    login: 'Login',
    watching: 'Watching',
    uptime: 'Uptime',
    not_watching: 'not watching',
    campaigns: 'Campaigns',
    active_campaigns: 'Active',
    claimed_drops: 'Claimed drops',
    ready_drops: 'Ready to claim',
    drops_total: 'Drops',
    drops_in_progress: 'In progress',
    drops_locked: 'Locked',
    channels: 'Channels',
    wanted_games: 'Wanted games',
    websockets: 'Websockets',
    account: 'Account & session',
    account_user: 'User',
    account_login: 'Login',
    account_state: 'Engine state',
    account_uptime: 'Uptime',
    account_api: 'Dashboard',
    account_session: 'Imported session',
    session_expires: 'valid until {when}',
    session_none: 'not imported',
    signin_panel: 'Twitch sign-in',
    signin_browser: 'Sign in with browser',
    signin_renew: 'Renew session',
    signin_cancel: 'Cancel sign-in',
    signin_open: 'Open sign-in page',
    signin_hint: 'On a headless miner, start a sign-in and open the page it serves to drive the browser from here.',
    signin_hint_active: 'A sign-in is running. Open the page below and sign in to Twitch there.',
    signin_hint_no_page: 'The sign-in browser is open on the miner itself.',
    signin_started: 'Sign-in started.',
    signin_renew_requested: 'Renewal requested.',
    signin_cancelled: 'Sign-in cancelled.',
    signin_unavailable: 'Cannot sign in: {message}',
    signin_renew_unavailable: 'Cannot renew: {message}',
    signin_session: 'Session',
    signin_renewal: 'Renewal',
    signin_renewal_auto: 'available with {browser}',
    signin_renewal_off: 'unavailable ({reason})',
    signin_renewal_error: 'last renewal failed: {error}',
    login_state_idle: 'not running',
    login_state_starting: 'starting the browser',
    login_state_waiting: 'waiting for a sign-in',
    login_state_signed_in: 'signed in, finishing',
    login_state_captured: 'done',
    login_state_failed: 'failed ({detail})',
    search_drops: 'Search drops',
    all_games: 'All games',
    inventory_empty: 'No drops match this filter.',
    rewards: 'Rewards',
    in_progress: 'In progress',
    ready: 'Ready',
    locked: 'Locked',
    allowed_channels: '{count} allowed channel(s)',
    current_drop: 'Current drop',
    nothing_mining: 'Nothing is being mined right now.',
    campaign: 'Campaign',
    drop: 'Drop',
    reward: 'Reward',
    minutes: '{current}/{required} min',
    quick_actions: 'Quick actions',
    pause: 'Pause',
    resume: 'Resume',
    refresh_inventory: 'Refresh inventory',
    unwatch: 'Stop watching',
    claim: 'Claim ready drops',
    exit: 'Exit miner',
    exit_confirm: 'Stop the miner? Mining ends until you start it again.',
    no_websockets: 'No websocket connections yet.',
    search_channels: 'Search channels',
    search_campaigns: 'Search campaigns',
    online_only: 'Online only',
    watchable_only: 'Watchable only',
    refresh: 'Refresh',
    watch: 'Watch',
    watching_badge: 'watching',
    acl_badge: 'ACL',
    drops_off_badge: 'drops off',
    viewers: 'viewers',
    pending: 'pending',
    offline: 'offline',
    filter_active: 'Active',
    filter_wanted: 'Wanted games',
    filter_all: 'All',
    claim_now: 'Claim',
    claimed: 'claimed',
    unlinked: 'account not linked',
    ends: 'ends {when}',
    availability: '{hours} h left to finish',
    settings_mining: 'Mining',
    priority: 'Priority list',
    priority_hint: 'One game per line, highest priority first.',
    exclude: 'Excluded games',
    exclude_hint: 'One game per line. These are never mined.',
    priority_mode: 'Priority mode',
    mode_priority_only: 'Priority list only',
    mode_ending_soonest: 'Ending soonest',
    mode_low_avbl_first: 'Least time left first',
    language: 'Miner language',
    proxy: 'HTTP proxy',
    proxy_hint: 'Leave empty for a direct connection.',
    connection_quality: 'Connection quality (0–2)',
    reload_interval: 'Inventory reload interval (minutes)',
    badges_emotes: 'Include badge and emote campaigns',
    drops_check: 'Extra available-drops check',
    drops_check_hint: 'Turn this off if channels stop being mined.',
    advanced: 'Advanced',
    login_server: 'Sign-in page endpoint',
    host: 'Host',
    port: 'Port',
    browser_path: 'Renewal browser path',
    browser_path_hint: 'Leave empty to find Chrome/Chromium automatically.',
    save: 'Save',
    saved: 'Saved.',
    save_failed: 'Could not save: {error}',
    api_info: 'API',
    api_enabled: 'Enabled',
    api_listening: 'Listening',
    api_bind: 'Bind address',
    api_url: 'Dashboard URL',
    api_token: 'Token',
    api_token_set: 'configured',
    api_auth: 'Authentication',
    api_auth_enabled: 'token required',
    api_auth_disabled: 'off',
    auth_none: 'no token auth',
    api_note: 'The token can only be changed from the CLI (api rotate).',
    yes: 'yes',
    no: 'no',
    logs: 'Logs',
    follow: 'Follow',
    clear_view: 'Clear view',
    no_channels: 'No channels match this filter.',
    no_campaigns: 'No campaigns match this filter.',
    loading: 'Loading…',
    paused: 'Mining paused.',
    resumed: 'Mining resumed.',
    refreshed: 'Inventory refresh requested.',
    unwatched: 'Stopped watching.',
    claimed_result: 'Claimed {claimed} drop(s), {failed} failed.',
    exiting: 'The miner is exiting.',
    action_failed: 'Action failed: {error}',
    footer: 'TwitchDropsMiner web add-on',
    tab_refreshed: 'Refreshed.',
  },
  'zh-CN': {
    gate_hint: '输入矿工控制台里 `api token` 显示的管理口令。',
    token_placeholder: '接口口令',
    remember: '在此浏览器记住',
    connect: '连接',
    connecting: '连接中…',
    invalid_token: '口令不正确。',
    connection_failed: '无法连接矿工。',
    disconnect: '断开',
    tab_overview: '概览',
    tab_inventory: '掉宝仓库',
    tab_channels: '频道',
    tab_campaigns: '活动',
    tab_settings: '设置',
    tab_logs: '日志',
    engine: '引擎',
    login: '登录',
    watching: '观看',
    uptime: '运行',
    not_watching: '未观看',
    campaigns: '活动',
    active_campaigns: '进行中',
    claimed_drops: '已领取掉宝',
    ready_drops: '可领取',
    drops_total: '掉宝总数',
    drops_in_progress: '进行中',
    drops_locked: '未解锁',
    channels: '频道',
    wanted_games: '目标游戏',
    websockets: 'Websocket',
    account: '账号与会话',
    account_user: '用户',
    account_login: '登录',
    account_state: '引擎状态',
    account_uptime: '运行时长',
    account_api: '控制台地址',
    account_session: '导入会话',
    session_expires: '有效至 {when}',
    session_none: '尚未导入',
    signin_panel: 'Twitch 登录',
    signin_browser: '用浏览器登录',
    signin_renew: '续签会话',
    signin_cancel: '取消登录',
    signin_open: '打开登录页面',
    signin_hint: '无头机器上可以先发起登录，再打开它提供的页面，在网页里操作登录浏览器。',
    signin_hint_active: '登录进行中。打开下面的页面，在那里登录 Twitch。',
    signin_hint_no_page: '登录浏览器已经在矿工本机打开。',
    signin_started: '登录已启动。',
    signin_renew_requested: '已请求续签。',
    signin_cancelled: '已取消登录。',
    signin_unavailable: '无法登录：{message}',
    signin_renew_unavailable: '无法续签：{message}',
    signin_session: '会话',
    signin_renewal: '续签',
    signin_renewal_auto: '可用（{browser}）',
    signin_renewal_off: '不可用（{reason}）',
    signin_renewal_error: '上次续签失败：{error}',
    login_state_idle: '未运行',
    login_state_starting: '正在启动浏览器',
    login_state_waiting: '等待登录',
    login_state_signed_in: '已登录，正在完成',
    login_state_captured: '完成',
    login_state_failed: '失败（{detail}）',
    search_drops: '搜索掉宝',
    all_games: '全部游戏',
    inventory_empty: '没有符合筛选条件的掉宝。',
    rewards: '奖励',
    in_progress: '进行中',
    ready: '可领取',
    locked: '未解锁',
    allowed_channels: '限定 {count} 个频道',
    current_drop: '当前掉宝',
    nothing_mining: '当前没有在挖任何掉宝。',
    campaign: '活动',
    drop: '掉宝',
    reward: '奖励',
    minutes: '{current}/{required} 分钟',
    quick_actions: '快捷操作',
    pause: '暂停',
    resume: '继续',
    refresh_inventory: '刷新库存',
    unwatch: '停止观看',
    claim: '领取可领取掉宝',
    exit: '退出矿工',
    exit_confirm: '要停止矿工吗？停止后需要重新启动才会继续挖宝。',
    no_websockets: '还没有 websocket 连接。',
    search_channels: '搜索频道',
    search_campaigns: '搜索活动',
    online_only: '只看在线',
    watchable_only: '只看可挖',
    refresh: '刷新',
    watch: '观看',
    watching_badge: '观看中',
    acl_badge: '限定',
    drops_off_badge: '无掉宝',
    viewers: '观众',
    pending: '即将开播',
    offline: '离线',
    filter_active: '进行中',
    filter_wanted: '目标游戏',
    filter_all: '全部',
    claim_now: '领取',
    claimed: '已领取',
    unlinked: '账号未关联',
    ends: '{when} 结束',
    availability: '剩余 {hours} 小时可完成',
    settings_mining: '挖宝',
    priority: '优先级列表',
    priority_hint: '每行一个游戏，越靠前优先级越高。',
    exclude: '排除的游戏',
    exclude_hint: '每行一个游戏，这些游戏永远不会被挖。',
    priority_mode: '优先级模式',
    mode_priority_only: '只挖优先级列表',
    mode_ending_soonest: '最快结束优先',
    mode_low_avbl_first: '剩余时间最少优先',
    language: '矿工语言',
    proxy: 'HTTP 代理',
    proxy_hint: '留空表示直连。',
    connection_quality: '连接质量（0–2）',
    reload_interval: '库存刷新间隔（分钟）',
    badges_emotes: '包含徽章/表情活动',
    drops_check: '额外的掉宝可用性检查',
    drops_check_hint: '如果频道不再被挖，请关闭此项。',
    advanced: '高级',
    login_server: '登录页面',
    host: '地址',
    port: '端口',
    browser_path: '续签浏览器路径',
    browser_path_hint: '留空则自动查找 Chrome/Chromium。',
    save: '保存',
    saved: '已保存。',
    save_failed: '保存失败：{error}',
    api_info: '接口',
    api_enabled: '已启用',
    api_listening: '监听中',
    api_bind: '绑定地址',
    api_url: '控制台地址',
    api_token: '口令',
    api_token_set: '已设置',
    api_auth: '认证',
    api_auth_enabled: '需要口令',
    api_auth_disabled: '已关闭',
    auth_none: '未启用口令',
    api_note: '口令只能在 CLI 里更换（api rotate）。',
    yes: '是',
    no: '否',
    logs: '日志',
    follow: '跟随',
    clear_view: '清空显示',
    no_channels: '没有符合筛选条件的频道。',
    no_campaigns: '没有符合筛选条件的活动。',
    loading: '加载中…',
    paused: '已暂停挖宝。',
    resumed: '已继续挖宝。',
    refreshed: '已请求刷新库存。',
    unwatched: '已停止观看。',
    claimed_result: '领取成功 {claimed} 个，失败 {failed} 个。',
    exiting: '矿工正在退出。',
    action_failed: '操作失败：{error}',
    footer: 'TwitchDropsMiner 网页插件',
    tab_refreshed: '已刷新。',
  },
};

I18N['zh-TW'] = {
  ...I18N['zh-CN'],
  gate_hint: '輸入礦工主控台裡 `api token` 顯示的管理口令。',
  token_placeholder: '介面口令',
  remember: '在此瀏覽器記住',
  connect: '連線',
  connecting: '連線中…',
  invalid_token: '口令不正確。',
  connection_failed: '無法連線礦工。',
  disconnect: '中斷',
  tab_overview: '總覽',
  tab_inventory: '掉寶倉庫',
  tab_channels: '頻道',
  tab_campaigns: '活動',
  tab_settings: '設定',
  tab_logs: '日誌',
  engine: '引擎',
  login: '登入',
  watching: '觀看',
  uptime: '執行',
  not_watching: '未觀看',
  campaigns: '活動',
  active_campaigns: '進行中',
  claimed_drops: '已領取掉寶',
  ready_drops: '可領取',
  drops_total: '掉寶總數',
  drops_in_progress: '進行中',
  drops_locked: '未解鎖',
  channels: '頻道',
  wanted_games: '目標遊戲',
  account: '帳號與工作階段',
  account_user: '使用者',
  account_login: '登入',
  account_state: '引擎狀態',
  account_uptime: '執行時間',
  account_api: '主控台位址',
  account_session: '匯入工作階段',
  session_expires: '有效至 {when}',
  session_none: '尚未匯入',
  signin_panel: 'Twitch 登入',
  signin_browser: '用瀏覽器登入',
  signin_renew: '續簽工作階段',
  signin_cancel: '取消登入',
  signin_open: '開啟登入頁面',
  signin_hint: '無頭機器上可以先發起登入，再開啟它提供的頁面，在網頁裡操作登入瀏覽器。',
  signin_hint_active: '登入進行中。開啟下面的頁面，在那裡登入 Twitch。',
  signin_hint_no_page: '登入瀏覽器已經在礦工本機開啟。',
  signin_started: '登入已啟動。',
  signin_renew_requested: '已要求續簽。',
  signin_cancelled: '已取消登入。',
  signin_unavailable: '無法登入：{message}',
  signin_renew_unavailable: '無法續簽：{message}',
  signin_session: '工作階段',
  signin_renewal: '續簽',
  signin_renewal_auto: '可用（{browser}）',
  signin_renewal_off: '不可用（{reason}）',
  signin_renewal_error: '上次續簽失敗：{error}',
  login_state_idle: '未執行',
  login_state_starting: '正在啟動瀏覽器',
  login_state_waiting: '等待登入',
  login_state_signed_in: '已登入，正在完成',
  login_state_captured: '完成',
  login_state_failed: '失敗（{detail}）',
  search_drops: '搜尋掉寶',
  all_games: '全部遊戲',
  inventory_empty: '沒有符合篩選條件的掉寶。',
  rewards: '獎勵',
  in_progress: '進行中',
  ready: '可領取',
  locked: '未解鎖',
  allowed_channels: '限定 {count} 個頻道',
  current_drop: '目前掉寶',
  nothing_mining: '目前沒有在挖任何掉寶。',
  quick_actions: '快速操作',
  pause: '暫停',
  resume: '繼續',
  refresh_inventory: '重新整理庫存',
  unwatch: '停止觀看',
  claim: '領取可領取掉寶',
  exit: '結束礦工',
  exit_confirm: '要停止礦工嗎？停止後需要重新啟動才會繼續挖寶。',
  no_websockets: '還沒有 websocket 連線。',
  search_channels: '搜尋頻道',
  search_campaigns: '搜尋活動',
  online_only: '只看在線',
  watchable_only: '只看可挖',
  refresh: '重新整理',
  watch: '觀看',
  watching_badge: '觀看中',
  acl_badge: '限定',
  drops_off_badge: '無掉寶',
  viewers: '觀眾',
  pending: '即將開播',
  offline: '離線',
  filter_active: '進行中',
  filter_wanted: '目標遊戲',
  filter_all: '全部',
  claim_now: '領取',
  claimed: '已領取',
  unlinked: '帳號未關聯',
  ends: '{when} 結束',
  availability: '剩餘 {hours} 小時可完成',
  settings_mining: '挖寶',
  priority: '優先順序列表',
  priority_hint: '每行一個遊戲，越前面優先順序越高。',
  exclude: '排除的遊戲',
  exclude_hint: '每行一個遊戲，這些遊戲永遠不會被挖。',
  priority_mode: '優先順序模式',
  mode_priority_only: '只挖優先順序列表',
  mode_ending_soonest: '最快結束優先',
  mode_low_avbl_first: '剩餘時間最少優先',
  language: '礦工語言',
  proxy: 'HTTP 代理',
  proxy_hint: '留空表示直連。',
  connection_quality: '連線品質（0–2）',
  reload_interval: '庫存重新整理間隔（分鐘）',
  badges_emotes: '包含徽章/表情活動',
  drops_check: '額外的掉寶可用性檢查',
  drops_check_hint: '如果頻道不再被挖，請關閉此項。',
  advanced: '進階',
  login_server: '登入頁面',
  host: '位址',
  port: '連接埠',
  browser_path: '續簽瀏覽器路徑',
  browser_path_hint: '留空則自動尋找 Chrome/Chromium。',
  save: '儲存',
  saved: '已儲存。',
  save_failed: '儲存失敗：{error}',
  api_info: '介面',
  api_enabled: '已啟用',
  api_listening: '監聽中',
  api_bind: '綁定位址',
  api_url: '主控台位址',
  api_token: '口令',
  api_token_set: '已設定',
  api_auth: '認證',
  api_auth_enabled: '需要口令',
  api_auth_disabled: '已關閉',
  auth_none: '未啟用口令',
  api_note: '口令只能在 CLI 裡更換（api rotate）。',
  yes: '是',
  no: '否',
  logs: '日誌',
  follow: '跟隨',
  clear_view: '清除顯示',
  no_channels: '沒有符合篩選條件的頻道。',
  no_campaigns: '沒有符合篩選條件的活動。',
  loading: '載入中…',
  paused: '已暫停挖寶。',
  resumed: '已繼續挖寶。',
  refreshed: '已要求重新整理庫存。',
  unwatched: '已停止觀看。',
  claimed_result: '領取成功 {claimed} 個，失敗 {failed} 個。',
  exiting: '礦工正在結束。',
  action_failed: '操作失敗：{error}',
  footer: 'TwitchDropsMiner 網頁外掛',
  tab_refreshed: '已重新整理。',
};

const state = {
  token: '',
  status: null,
  channels: [],
  campaigns: [],
  settings: null,
  api: null,
  login: null,
  logs: [],
  tab: 'overview',
  lang: 'en',
  eventAbort: null,
  eventRetry: null,
  pollTimer: null,
  loginPoll: null,
  authRequired: true,
};

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === '') continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

function t(key, vars = {}) {
  const table = I18N[state.lang] || I18N.en;
  let text = table[key] ?? I18N.en[key] ?? key;
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

function pct(value) {
  return `${Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100)}%`;
}

function progressBar(value, thin = false) {
  const bar = el('div', { class: thin ? 'bar thin' : 'bar' });
  bar.append(el('i', { style: `width:${pct(value)}` }));
  return bar;
}

function formatUptime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (days) return `${days}d ${hours}h ${minutes}m`;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

function formatDate(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(state.lang, { dateStyle: 'medium', timeStyle: 'short' });
}

function splitList(text) {
  return text
    .split(/[\n,]+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function splitLines(text) {
  return text
    .split(/\n+/)
    .map((part) => part.trim())
    .filter(Boolean);
}

let toastTimer = null;
function toast(message, isError = false) {
  const node = $('#toast');
  node.textContent = message;
  node.classList.toggle('error', isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.hidden = true;
  }, isError ? 6500 : 3200);
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

function authHeaders(extra = {}) {
  return { 'X-API-Token': state.token, ...extra };
}

async function apiGet(path) {
  const response = await fetch(path, { headers: authHeaders(), cache: 'no-store' });
  if (response.status === 401) {
    logout(true);
    throw new Error(t('invalid_token'));
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
  return data;
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body || {}),
  });
  if (response.status === 401) {
    logout(true);
    throw new Error(t('invalid_token'));
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`);
  return data;
}

async function checkAuthRequired() {
  try {
    const response = await fetch('/auth', { cache: 'no-store' });
    if (!response.ok) return true;
    const data = await response.json();
    return data.required !== false;
  } catch {
    return true;
  }
}

async function loadStatus() {
  state.status = await apiGet('/api/status');
  renderHeader();
  renderOverview();
}

async function loadChannels() {
  const data = await apiGet('/api/channels');
  state.channels = data.channels || [];
  renderChannels();
}

async function loadCampaigns() {
  const data = await apiGet('/api/campaigns');
  state.campaigns = data.campaigns || [];
  renderCampaigns();
  renderInventory();
}

async function loadSettings() {
  const data = await apiGet('/api/settings');
  state.settings = data.settings || {};
  state.api = data.api || {};
  renderSettings();
  renderApiInfo();
}

async function loadLogin() {
  state.login = await apiGet('/api/login');
  renderLogin();
  scheduleLoginPoll();
}

async function loadLogs() {
  const data = await apiGet('/api/logs?limit=400');
  state.logs = data.lines || [];
  renderLogs();
}

// ---------------------------------------------------------------------------
// connection, SSE
// ---------------------------------------------------------------------------

async function connect(token) {
  state.token = token;
  const data = await apiGet('/api/status');
  state.status = data;
  $('#gate').hidden = true;
  $('#app').hidden = false;
  await Promise.all([loadChannels(), loadCampaigns(), loadSettings(), loadLogin(), loadLogs()]);
  renderHeader();
  renderOverview();
  startEvents();
}

function logout(expired = false) {
  if (!state.authRequired) {
    // There is no gate to return to; reloading picks up the current mode.
    location.reload();
    return;
  }
  state.token = '';
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_SESSION_KEY);
  if (state.loginPoll) {
    clearTimeout(state.loginPoll);
    state.loginPoll = null;
  }
  stopEvents();
  $('#app').hidden = true;
  $('#gate').hidden = false;
  const error = $('#gate-error');
  error.hidden = !expired;
  error.textContent = expired ? t('invalid_token') : '';
  $('#gate-token').value = '';
  $('#gate-token').focus();
}

function showGate() {
  $('#gate').hidden = false;
  $('#app').hidden = true;
  $('#gate-token').focus();
}

function stopEvents() {
  if (state.eventAbort) {
    state.eventAbort.abort();
    state.eventAbort = null;
  }
  if (state.eventRetry) {
    clearTimeout(state.eventRetry);
    state.eventRetry = null;
  }
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function startEvents() {
  stopEvents();
  const controller = new AbortController();
  state.eventAbort = controller;
  (async () => {
    try {
      const response = await fetch('/api/events', {
        headers: authHeaders(),
        cache: 'no-store',
        signal: controller.signal,
      });
      if (response.status === 401) {
        logout(true);
        return;
      }
      if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let split;
        while ((split = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          let event = 'message';
          let payload = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) payload += line.slice(5).trim();
          }
          if (!payload) continue;
          let data;
          try {
            data = JSON.parse(payload);
          } catch {
            continue;
          }
          if (event === 'status') {
            state.status = data;
            renderHeader();
            renderOverview();
          } else if (event === 'logs') {
            state.logs = data.lines || [];
            renderLogs();
          }
        }
      }
    } catch (error) {
      if (controller.signal.aborted) return;
    }
    if (state.token) {
      state.eventRetry = setTimeout(startEvents, 4000);
      // SSE may be blocked by a proxy; fall back to polling while it retries.
      if (!state.pollTimer) {
        state.pollTimer = setInterval(() => {
          if (!state.token) return;
          loadStatus().catch(() => {});
          loadLogs().catch(() => {});
        }, 5000);
      }
    }
  })();
}

// ---------------------------------------------------------------------------
// rendering
// ---------------------------------------------------------------------------

function isPaused() {
  return state.status?.state === 'IDLE';
}

function renderToggle() {
  const button = $('#toggle-mining');
  if (!button) return;
  const paused = isPaused();
  button.textContent = paused ? t('resume') : t('pause');
  button.dataset.mode = paused ? 'resume' : 'pause';
  button.disabled = state.status?.state === 'EXIT';
}

function renderHeader() {
  const status = state.status;
  if (!status) return;
  renderToggle();
  const chipAuth = $('#chip-auth');
  chipAuth.hidden = state.authRequired;
  chipAuth.textContent = state.authRequired ? '' : t('auth_none');
  $('#version').textContent = status.version || '';
  const stateName =
    status.state === 'CHANNEL_SWITCH' && status.watching ? 'WATCHING' : status.state;
  const chipState = $('#chip-state');
  chipState.textContent = `${t('engine')}: ${stateName}`;
  chipState.className =
    'chip ' + (stateName === 'WATCHING' ? 'ok' : stateName === 'EXIT' ? 'bad' : 'warn');

  const login = state.login || {};
  const userId = status.login?.user_id || login.user_id;
  const chipLogin = $('#chip-login');
  chipLogin.textContent = `${t('login')}: ${userId || status.login?.status || '—'}`;
  chipLogin.className = 'chip ' + (userId ? 'ok' : 'warn');

  const chipWatching = $('#chip-watching');
  chipWatching.textContent = `${t('watching')}: ${
    status.watching?.name || status.watching?.login || t('not_watching')
  }`;
  chipWatching.className = 'chip ' + (status.watching ? 'ok' : '');

  $('#chip-uptime').textContent = `${t('uptime')}: ${formatUptime(status.uptime_seconds)}`;
}

function renderOverview() {
  const status = state.status;
  if (!status) return;
  $('#stat-campaigns').textContent = status.counts?.campaigns ?? '—';
  $('#stat-active').textContent = status.counts?.active_campaigns ?? '—';
  $('#stat-claimed').textContent = status.counts?.claimed_drops ?? '—';
  $('#stat-ready').textContent = status.counts?.claimable_drops ?? '—';
  $('#stat-channels').textContent = status.counts?.channels ?? '—';
  $('#stat-ws').textContent = status.counts?.websockets ?? '—';

  const container = clear($('#current-drop'));
  const progress = status.progress;
  if (!progress) {
    container.append(el('p', { class: 'empty', text: t('nothing_mining') }));
    $('#current-game').textContent = '';
  } else {
    const { drop, campaign } = progress;
    $('#current-game').textContent = campaign.game || '';
    container.append(
      el('div', { class: 'drop-title' },
        el('strong', { text: drop.name }),
        el('span', { class: 'muted', text: t('reward') + ': ' + (drop.rewards || '—') }),
      ),
      el('div', { class: 'row' },
        el('span', { text: t('drop') }),
        progressBar(drop.progress),
        el('span', { class: 'muted', text: t('minutes', { current: drop.current_minutes, required: drop.required_minutes }) }),
      ),
      el('div', { class: 'row' },
        el('span', { text: t('campaign') }),
        progressBar(campaign.progress),
        el('span', { class: 'muted', text: `${campaign.claimed_drops}/${campaign.total_drops} ${t('claimed')}` }),
      ),
    );
  }

  const wanted = clear($('#wanted-games'));
  if (!status.wanted_games?.length) wanted.append(el('span', { class: 'empty', text: '—' }));
  for (const name of status.wanted_games || []) {
    wanted.append(el('span', { class: 'pill', text: name }));
  }

  const ws = clear($('#ws-list'));
  if (!status.websockets?.length) {
    ws.append(el('div', { class: 'muted', text: t('no_websockets') }));
  }
  for (const entry of status.websockets || []) {
    ws.append(
      el('div', { class: 'ws-item' },
        el('span', { text: `#${entry.idx} ${entry.status}` }),
        el('span', { text: `${entry.topics} topics` }),
      ),
    );
  }

  renderAccount();
}

function kvRow(key, value) {
  return [
    el('span', { class: 'k', text: key }),
    el('span', { class: 'v', text: value ?? '—' }),
  ];
}

function renderAccount() {
  const container = clear($('#account-info'));
  const status = state.status;
  const login = state.login || {};
  const session = login.active && login.expires_at
    ? t('session_expires', { when: formatDate(new Date(login.expires_at * 1000).toISOString()) })
    : t('session_none');
  const rows = [
    kvRow(t('account_user'), login.user_id || status?.login?.user_id),
    kvRow(t('account_login'), status?.login?.status),
    kvRow(t('account_state'), status?.state),
    kvRow(t('account_uptime'), formatUptime(status?.uptime_seconds)),
    kvRow(t('account_session'), session),
  ];
  for (const row of rows) container.append(...row);
}

function channelRow(channel) {
  const onlineClass = channel.online ? 'online' : channel.pending_online ? 'pending' : 'offline';
  const badges = el('div', { class: 'row-title' },
    el('span', { class: `dot ${onlineClass}` }),
    el('strong', { text: channel.name }),
    channel.watching ? el('span', { class: 'badge accent', text: t('watching_badge') }) : null,
    channel.acl_based ? el('span', { class: 'badge', text: t('acl_badge') }) : null,
    channel.online && !channel.drops_enabled
      ? el('span', { class: 'badge amber', text: t('drops_off_badge') })
      : null,
    !channel.online ? el('span', { class: 'badge', text: t('offline') }) : null,
  );
  const sub = el('div', { class: 'row-sub' },
    [channel.game?.name || '—', channel.viewers !== null ? `${channel.viewers} ${t('viewers')}` : null]
      .filter(Boolean)
      .join(' · '),
  );
  const side = el('div', { class: 'row-side' });
  if (channel.watching) {
    side.append(el('span', { class: 'badge green', text: t('watching_badge') }));
  } else {
    side.append(
      el('button', {
        type: 'button',
        class: 'small',
        text: t('watch'),
        disabled: channel.can_watch ? null : '',
        onclick: () => selectChannel(channel),
      }),
    );
  }
  return el('div', { class: `row-card${channel.watching ? ' watching' : ''}` },
    el('div', { class: 'row-main' }, badges, sub),
    side,
  );
}

function renderChannels() {
  const container = clear($('#channel-list'));
  const query = $('#channel-search').value.trim().toLowerCase();
  const onlineOnly = $('#channels-online').checked;
  const watchableOnly = $('#channels-watchable').checked;
  const list = state.channels
    .filter((channel) => {
      if (onlineOnly && !channel.online) return false;
      if (watchableOnly && !channel.can_watch) return false;
      if (!query) return true;
      return [channel.name, channel.login, channel.game?.name]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query));
    })
    .sort((a, b) => {
      if (a.watching !== b.watching) return a.watching ? -1 : 1;
      if (a.online !== b.online) return a.online ? -1 : 1;
      return (b.viewers || 0) - (a.viewers || 0);
    });
  if (!list.length) {
    container.append(el('p', { class: 'empty', text: t('no_channels') }));
    return;
  }
  for (const channel of list) container.append(channelRow(channel));
}

function campaignCard(campaign) {
  const art = cachedImage(campaign, 'campaign-art');
  const head = el('div', { class: 'campaign-head' },
    art,
    el('span', { class: 'game', text: campaign.game?.name || '—' }),
    el('span', { class: 'name', text: campaign.name }),
    el('span', { class: 'badge accent', text: `${campaign.claimed_drops}/${campaign.total_drops}` }),
    campaign.allowed_channels?.length
      ? el('span', { class: 'badge', text: t('allowed_channels', { count: campaign.allowed_channels.length }) })
      : null,
    !campaign.linked ? el('span', { class: 'badge amber', text: t('unlinked') }) : null,
    campaign.finished ? el('span', { class: 'badge green', text: t('claimed') }) : null,
  );
  const meta = el('div', { class: 'campaign-meta' },
    el('span', { text: t('ends', { when: formatDate(campaign.ends_at) }) }),
    Number.isFinite(Number(campaign.availability))
      ? el('span', { text: t('availability', { hours: Math.round(campaign.availability) }) })
      : null,
  );
  const drops = el('div', { class: 'drops' });
  for (const drop of campaign.drops) {
    const claimButton = drop.claimable
      ? el('button', {
          type: 'button',
          class: 'small',
          text: t('claim_now'),
          onclick: () => claimDrop(drop),
        })
      : null;
    drops.append(
      el('div', { class: 'drop-row' },
        el('div', { class: 'drop-name' },
          el('div', { class: 'drop-title-line' },
            el('span', { text: drop.name }),
            drop.claimed ? el('span', { class: 'badge green', text: t('claimed') }) : null,
            rewardArt(drop.benefits),
          ),
          drop.rewards
            ? el('div', { class: 'drop-rewards', text: drop.rewards })
            : null,
        ),
        el('div', { class: 'drop-progress' },
          progressBar(drop.progress, true),
          el('span', { class: 'drop-minutes', text: t('minutes', { current: drop.current_minutes, required: drop.required_minutes }) }),
        ),
        claimButton || el('span', { class: 'muted', text: pct(drop.progress) }),
      ),
    );
  }
  return el('article', { class: `campaign${campaign.finished ? ' finished' : ''}` },
    head,
    progressBar(campaign.progress),
    meta,
    drops,
  );
}

function renderCampaigns() {
  const container = clear($('#campaign-list'));
  const query = $('#campaign-search').value.trim().toLowerCase();
  const filter = $('#campaign-filter').value;
  const wanted = new Set(state.status?.wanted_games || []);
  const list = state.campaigns
    .filter((campaign) => {
      if (filter === 'active' && (!campaign.active || campaign.finished)) return false;
      if (filter === 'wanted' && !wanted.has(campaign.game?.name)) return false;
      if (!query) return true;
      return (
        campaign.name.toLowerCase().includes(query) ||
        (campaign.game?.name || '').toLowerCase().includes(query) ||
        campaign.drops.some((drop) => drop.name.toLowerCase().includes(query))
      );
    })
    .sort((a, b) => {
      if (a.active !== b.active) return a.active ? -1 : 1;
      if (a.finished !== b.finished) return a.finished ? 1 : -1;
      return (a.game?.name || '').localeCompare(b.game?.name || '') || a.name.localeCompare(b.name);
    });
  if (!list.length) {
    container.append(el('p', { class: 'empty', text: t('no_campaigns') }));
    return;
  }
  for (const campaign of list) container.append(campaignCard(campaign));
}

function loginStateLabel(login) {
  const status = login?.login_state || 'idle';
  if (status === 'failed') {
    return t('login_state_failed', { detail: login?.login_detail || '?' });
  }
  return t(`login_state_${status}`);
}

function signinURL(login) {
  const urls = login?.urls || [];
  if (!urls.length) return '';
  // The dashboard proxies /login/* through its own port, so keep only the path
  // and put it on the origin the dashboard itself is open at. That is what
  // removes the need to forward the sign-in port separately.
  let chosen = urls[0];
  const match = urls.find((url) => {
    try {
      return new URL(url).hostname === location.hostname;
    } catch {
      return false;
    }
  });
  if (match) chosen = match;
  try {
    const parsed = new URL(chosen);
    return `${location.origin}${parsed.pathname}${parsed.search}`;
  } catch {
    return chosen;
  }
}

function renderLogin() {
  const login = state.login;
  if (!login) return;
  const status = login.login_state || 'idle';
  $('#signin-state').textContent = loginStateLabel(login);

  const info = clear($('#signin-info'));
  const session = login.active && login.expires_at
    ? t('session_expires', {
        when: formatDate(new Date(login.expires_at * 1000).toISOString()),
      })
    : t('session_none');
  const renewal = login.renewal_unavailable
    ? t('signin_renewal_off', { reason: login.renewal_unavailable })
    : login.browser
      ? t('signin_renewal_auto', { browser: login.browser })
      : t('signin_renewal_off', { reason: '?' });
  const rows = [
    kvRow(t('signin_session'), session),
    kvRow(t('signin_renewal'), renewal),
  ];
  if (login.renewal_error) {
    rows.push(kvRow(t('signin_renewal_error'), login.renewal_error));
  }
  for (const row of rows) info.append(...row);

  const active = ['starting', 'waiting', 'signed_in'].includes(status);
  const link = signinURL(login);
  const open = $('#signin-open');
  open.hidden = !link;
  if (link) open.href = link;
  $('#signin-cancel').hidden = !active;
  $('#signin-browser').disabled = active;
  $('#signin-renew').disabled = !login.active || Boolean(login.renewal_unavailable);
  $('#signin-hint').textContent = active
    ? (link ? t('signin_hint_active') : t('signin_hint_no_page'))
    : t('signin_hint');

  // Embed the viewer only while a sign-in is running; blank it afterwards so
  // the page stops streaming and drops its sign-in cookie.
  const viewer = $('#signin-viewer');
  const frame = $('#signin-frame');
  const showViewer = active && Boolean(link);
  viewer.hidden = !showViewer;
  if (showViewer) {
    if (frame.dataset.url !== link) {
      frame.dataset.url = link;
      frame.src = link;
    }
  } else if (frame.dataset.url) {
    frame.dataset.url = '';
    frame.src = 'about:blank';
  }
}

function scheduleLoginPoll() {
  const status = state.login?.login_state || '';
  const active = ['starting', 'waiting', 'signed_in'].includes(status);
  if (!active) {
    if (state.loginPoll) {
      clearTimeout(state.loginPoll);
      state.loginPoll = null;
    }
    return;
  }
  if (state.loginPoll) return;
  state.loginPoll = setTimeout(async () => {
    state.loginPoll = null;
    try {
      await loadLogin();
      await loadStatus();
      if (state.login?.login_state === 'captured' || state.login?.active) {
        await loadCampaigns();
      }
    } catch {
      // The next poll or the user's next action will pick it up.
    }
  }, 2000);
}

async function loginAction(action, successKey) {
  try {
    await apiPost(`/api/actions/${action}`);
    toast(t(successKey));
    await loadLogin();
    await loadStatus();
  } catch (error) {
    const key = action === 'login-renew' ? 'signin_renew_unavailable' : 'signin_unavailable';
    toast(t(key, { message: error.message }), true);
  }
}

function dropStatus(drop) {
  if (drop.claimed) return 'claimed';
  if (drop.claimable) return 'ready';
  if (drop.can_earn) return 'progress';
  return 'locked';
}

function inventoryEntries() {
  const entries = [];
  for (const campaign of state.campaigns) {
    for (const drop of campaign.drops) {
      entries.push({ campaign, drop, status: dropStatus(drop) });
    }
  }
  return entries;
}

function cachedImage(item, className, alt = '') {
  const source = item?.cached_image_url || item?.image_url;
  if (!source) return null;
  const fallback = item?.image_url && item.image_url !== source ? item.image_url : '';
  return el('img', {
    class: className,
    src: source,
    alt,
    title: alt || null,
    loading: 'lazy',
    referrerpolicy: 'no-referrer',
    dataset: { fallback },
    onerror: (event) => {
      const image = event.target;
      // The miner's cache may be unavailable; fall back to the CDN once.
      if (image.dataset.fallback) {
        image.src = image.dataset.fallback;
        image.dataset.fallback = '';
      } else {
        image.hidden = true;
      }
    },
  });
}

function rewardArt(benefits, limit = 3) {
  const withImage = (benefits || []).filter(
    (benefit) => benefit?.cached_image_url || benefit?.image_url,
  );
  if (!withImage.length) return null;
  const row = el('span', { class: 'reward-art' });
  for (const benefit of withImage.slice(0, limit)) {
    row.append(cachedImage(benefit, 'reward-img', benefit.name));
  }
  if (withImage.length > limit) {
    row.append(el('span', {
      class: 'reward-more',
      text: `+${withImage.length - limit}`,
    }));
  }
  return row;
}

function statusBadge(status) {
  const label = {
    claimed: 'claimed', ready: 'ready', progress: 'in_progress', locked: 'locked',
  }[status] || status;
  const cls = {
    claimed: 'green', ready: 'accent', progress: 'amber', locked: '',
  }[status] || '';
  return el('span', { class: `badge ${cls}`.trim(), text: t(label) });
}

function fillInventoryGames() {
  const select = $('#inventory-game');
  if (!select) return;
  const current = select.value;
  const games = [...new Set(
    state.campaigns.map((campaign) => campaign.game?.name).filter(Boolean),
  )].sort();
  clear(select);
  select.append(el('option', { value: '', text: t('all_games') }));
  for (const game of games) select.append(el('option', { value: game, text: game }));
  select.value = games.includes(current) ? current : '';
}

function inventoryRow({ campaign, drop, status }) {
  const title = el('div', { class: 'row-title' },
    el('strong', { text: drop.name }),
    statusBadge(status),
    rewardArt(drop.benefits),
  );
  const sub = el('div', { class: 'row-sub' },
    `${campaign.game?.name || '—'} · ${campaign.name}`
      + (drop.rewards ? ` · ${t('rewards')}: ${drop.rewards}` : ''),
  );
  const progress = el('div', { class: 'drop-progress' },
    progressBar(drop.progress, true),
    el('span', { class: 'drop-minutes', text: t('minutes', {
      current: drop.current_minutes, required: drop.required_minutes,
    }) }),
  );
  const action = drop.claimable
    ? el('button', {
        type: 'button', class: 'small', text: t('claim_now'),
        onclick: () => claimDrop(drop),
      })
    : el('span', { class: 'muted', text: pct(drop.progress) });
  return el('div', { class: 'row-card inv-row' },
    el('div', { class: 'row-main' }, title, sub),
    progress,
    el('div', { class: 'row-side' }, action),
  );
}

function renderInventory() {
  const list = $('#inventory-list');
  if (!list) return;
  fillInventoryGames();
  const entries = inventoryEntries();
  const counts = {
    progress: entries.filter((entry) => entry.status === 'progress').length,
    ready: entries.filter((entry) => entry.status === 'ready').length,
    claimed: entries.filter((entry) => entry.status === 'claimed').length,
  };
  $('#inv-total').textContent = entries.length;
  $('#inv-progress').textContent = counts.progress;
  $('#inv-ready').textContent = counts.ready;
  $('#inv-claimed').textContent = counts.claimed;

  const query = $('#inventory-search').value.trim().toLowerCase();
  const statusFilter = $('#inventory-status').value;
  const gameFilter = $('#inventory-game').value;
  const filtered = entries
    .filter(({ campaign, drop, status }) => {
      if (statusFilter !== 'all' && status !== statusFilter) return false;
      if (gameFilter && campaign.game?.name !== gameFilter) return false;
      if (!query) return true;
      return [drop.name, campaign.name, campaign.game?.name, drop.rewards]
        .filter(Boolean)
        .some((value) => value.toLowerCase().includes(query));
    })
    .sort((a, b) => {
      const order = { ready: 0, progress: 1, locked: 2, claimed: 3 };
      if (order[a.status] !== order[b.status]) return order[a.status] - order[b.status];
      return String(a.campaign.ends_at || '').localeCompare(String(b.campaign.ends_at || ''));
    });

  clear(list);
  if (!filtered.length) {
    list.append(el('p', { class: 'empty', text: t('inventory_empty') }));
    return;
  }
  for (const entry of filtered) list.append(inventoryRow(entry));
}

function field(labelText, control, hint = null, wide = false) {
  return el('div', { class: wide ? 'field wide' : 'field' },
    el('label', { text: labelText }),
    control,
    hint ? el('span', { class: 'hint', text: hint }) : null,
  );
}

function renderSettings() {
  const container = clear($('#settings-form'));
  if (!state.settings) {
    container.append(el('span', { class: 'muted', text: t('loading') }));
    return;
  }
  const s = state.settings;
  const priority = el('textarea', { rows: '6' });
  priority.value = (s.priority || []).join('\n');
  const exclude = el('textarea', { rows: '4' });
  exclude.value = (s.exclude || []).join('\n');

  const mode = el('select', {},
    ...[
      ['priority_only', 'mode_priority_only'],
      ['ending_soonest', 'mode_ending_soonest'],
      ['low_avbl_first', 'mode_low_avbl_first'],
    ].map(([value, key]) => el('option', { value, text: t(key) })),
  );
  mode.value = s.priority_mode || 'priority_only';

  const languages = ['en', 'zh-CN', 'zh-TW'];
  if (s.language && !languages.includes(s.language)) languages.push(s.language);
  const language = el('select', {},
    ...languages.map((code) => el('option', { value: code, text: code })),
  );
  language.value = s.language || 'en';

  const proxy = el('input', { type: 'text', value: s.proxy || '' });
  const quality = el('input', { type: 'number', min: '0', max: '2', value: String(s.connection_quality ?? 1) });
  const interval = el('input', { type: 'number', min: '10', max: '1440', value: String(s.reload_interval ?? 60) });
  const badges = el('input', { type: 'checkbox' });
  badges.checked = Boolean(s.enable_badges_emotes);
  const dropsCheck = el('input', { type: 'checkbox' });
  dropsCheck.checked = Boolean(s.available_drops_check);

  const loginEnabled = el('input', { type: 'checkbox' });
  loginEnabled.checked = Boolean(s.login_server_enabled);
  const loginHost = el('input', { type: 'text', value: s.login_server_host || '' });
  const loginPort = el('input', { type: 'number', min: '1', max: '65535', value: String(s.login_server_port ?? 8090) });
  const browser = el('input', { type: 'text', value: s.renewal_browser_path || '' });

  container.append(
    field(t('priority'), priority, t('priority_hint'), true),
    field(t('exclude'), exclude, t('exclude_hint'), true),
    field(t('priority_mode'), mode),
    field(t('language'), language),
    field(t('proxy'), proxy, t('proxy_hint')),
    field(t('connection_quality'), quality),
    field(t('reload_interval'), interval),
    field(t('badges_emotes'), el('label', { class: 'check' }, badges, el('span', { text: t('badges_emotes') }))),
    field(t('drops_check'), el('label', { class: 'check' }, dropsCheck, el('span', { text: t('drops_check') })), t('drops_check_hint')),
    field(t('advanced'), el('label', { class: 'check' }, loginEnabled, el('span', { text: t('login_server') })), null, true),
    field(t('host'), loginHost),
    field(t('port'), loginPort),
    field(t('browser_path'), browser, t('browser_path_hint'), true),
  );

  $('#settings-save').onclick = async () => {
    const status = $('#settings-status');
    status.textContent = '…';
    const patch = {
      priority: splitLines(priority.value),
      exclude: splitLines(exclude.value),
      priority_mode: mode.value,
      language: language.value,
      proxy: proxy.value.trim(),
      connection_quality: Number(quality.value),
      reload_interval: Number(interval.value),
      enable_badges_emotes: badges.checked,
      available_drops_check: dropsCheck.checked,
      login_server_enabled: loginEnabled.checked,
      login_server_host: loginHost.value.trim(),
      login_server_port: Number(loginPort.value),
      renewal_browser_path: browser.value.trim(),
    };
    try {
      const data = await apiPost('/api/settings', patch);
      state.settings = data.settings || state.settings;
      status.textContent = t('saved');
      toast(t('saved'));
      await loadStatus();
    } catch (error) {
      status.textContent = '';
      toast(t('save_failed', { error: error.message }), true);
    }
  };
}

function renderApiInfo() {
  const container = clear($('#api-info'));
  const api = state.api || {};
  const token = state.settings?.api_token;
  const rows = [
    [t('api_enabled'), api.enabled ? t('yes') : t('no')],
    [t('api_listening'), api.listening ? t('yes') : t('no')],
    [t('api_bind'), api.bind || '—'],
    [t('api_url'), api.url || '—'],
    [t('api_auth'), api.auth ? t('api_auth_enabled') : t('api_auth_disabled')],
    [t('api_token'), token?.configured ? t('api_token_set') : '—'],
  ];
  for (const [key, value] of rows) {
    container.append(el('span', { class: 'k', text: key }), el('span', { class: 'v', text: value }));
  }
  container.append(el('span', { class: 'k' }), el('span', { class: 'v muted', text: t('api_note') }));
}

function renderLogs() {
  const view = $('#log-view');
  view.textContent = state.logs.join('\n');
  if ($('#log-follow').checked) view.scrollTop = view.scrollHeight;
}

// ---------------------------------------------------------------------------
// actions
// ---------------------------------------------------------------------------

async function selectChannel(channel) {
  try {
    await apiPost('/api/channels/select', { id: channel.id });
    toast(`${t('watch')}: ${channel.name}`);
    await Promise.all([loadStatus(), loadChannels()]);
  } catch (error) {
    toast(error.message, true);
  }
}

async function claimDrop(drop) {
  try {
    const data = await apiPost('/api/actions/claim', { drop_id: drop.id });
    toast(`${t('drop')}: ${drop.name} — ${data.claimed ? t('claimed') : '—'}`);
    await Promise.all([loadCampaigns(), loadStatus()]);
  } catch (error) {
    toast(error.message, true);
  }
}

async function runAction(action) {
  if (action === 'exit' && !window.confirm(t('exit_confirm'))) return;
  try {
    const data = await apiPost(`/api/actions/${action}`);
    if (action === 'pause') toast(t('paused'));
    else if (action === 'resume') toast(t('resumed'));
    else if (action === 'refresh') toast(t('refreshed'));
    else if (action === 'unwatch') toast(t('unwatched'));
    else if (action === 'claim') toast(t('claimed_result', { claimed: data.claimed ?? 0, failed: data.failed ?? 0 }));
    else if (action === 'exit') {
      toast(t('exiting'));
      stopEvents();
      return;
    }
    await Promise.all([loadStatus(), loadChannels(), loadCampaigns()]);
  } catch (error) {
    toast(t('action_failed', { error: error.message }), true);
  }
}

// ---------------------------------------------------------------------------
// language, theme, tabs, wiring
// ---------------------------------------------------------------------------

function detectLanguage() {
  const stored = localStorage.getItem(LANG_KEY);
  if (stored && I18N[stored]) return stored;
  const tag = (navigator.language || 'en').toLowerCase();
  if (tag.startsWith('zh-tw') || tag.startsWith('zh-hant')) return 'zh-TW';
  if (tag.startsWith('zh')) return 'zh-CN';
  return 'en';
}

function applyLanguage() {
  document.documentElement.lang = state.lang;
  for (const node of $$('[data-i18n]')) node.textContent = t(node.dataset.i18n);
  for (const node of $$('[data-i18n-placeholder]')) node.placeholder = t(node.dataset.i18nPlaceholder);
  $('#lang-select').value = state.lang;
  document.title = `TwitchDropsMiner Console`;
  renderHeader();
  renderOverview();
  renderLogin();
  renderChannels();
  renderCampaigns();
  renderInventory();
  renderSettings();
  renderApiInfo();
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
}

function switchTab(tab) {
  state.tab = tab;
  for (const button of $$('#tabs button')) {
    button.classList.toggle('active', button.dataset.tab === tab);
  }
  for (const section of $$('.tab')) {
    section.classList.toggle('active', section.id === `tab-${tab}`);
  }
  if (tab === 'inventory') {
    renderInventory();
    loadCampaigns().catch(() => {});
  }
  if (tab === 'channels') loadChannels().catch(() => {});
  if (tab === 'campaigns') loadCampaigns().catch(() => {});
  if (tab === 'settings') {
    loadSettings().catch(() => {});
    loadLogin().catch(() => {});
  }
  if (tab === 'logs') loadLogs().catch(() => {});
}

function bindEvents() {
  $('#gate-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const token = $('#gate-token').value.trim();
    if (!token) return;
    const error = $('#gate-error');
    const button = $('#gate-form button[type=submit]');
    error.hidden = true;
    button.disabled = true;
    button.textContent = t('connecting');
    try {
      if ($('#gate-remember').checked) {
        localStorage.setItem(TOKEN_KEY, token);
        sessionStorage.removeItem(TOKEN_SESSION_KEY);
      } else {
        sessionStorage.setItem(TOKEN_SESSION_KEY, token);
        localStorage.removeItem(TOKEN_KEY);
      }
      await connect(token);
    } catch (failure) {
      state.token = '';
      localStorage.removeItem(TOKEN_KEY);
      sessionStorage.removeItem(TOKEN_SESSION_KEY);
      error.hidden = false;
      error.textContent =
        failure.message === t('invalid_token') ? t('invalid_token') : t('connection_failed');
    } finally {
      button.disabled = false;
      button.textContent = t('connect');
    }
  });

  $('#disconnect').addEventListener('click', () => logout(false));
  $('#theme-toggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });
  $('#lang-select').addEventListener('change', (event) => {
    state.lang = event.target.value;
    localStorage.setItem(LANG_KEY, state.lang);
    applyLanguage();
  });
  for (const button of $$('#tabs button')) {
    button.addEventListener('click', () => switchTab(button.dataset.tab));
  }
  for (const button of $$('[data-action]')) {
    button.addEventListener('click', () => runAction(button.dataset.action));
  }
  $('#toggle-mining').addEventListener('click', () => {
    runAction(isPaused() ? 'resume' : 'pause');
  });
  $('#signin-browser').addEventListener('click', () => {
    loginAction('login-browser', 'signin_started');
  });
  $('#signin-renew').addEventListener('click', () => {
    loginAction('login-renew', 'signin_renew_requested');
  });
  $('#signin-cancel').addEventListener('click', () => {
    loginAction('login-cancel', 'signin_cancelled');
  });
  $('#inventory-search').addEventListener('input', renderInventory);
  $('#inventory-status').addEventListener('change', renderInventory);
  $('#inventory-game').addEventListener('change', renderInventory);
  $('#inventory-refresh').addEventListener('click', () => loadCampaigns().catch(() => {}));
  $('#channel-search').addEventListener('input', renderChannels);
  $('#channels-online').addEventListener('change', renderChannels);
  $('#channels-watchable').addEventListener('change', renderChannels);
  $('#channels-refresh').addEventListener('click', () => loadChannels().catch(() => {}));
  $('#campaign-search').addEventListener('input', renderCampaigns);
  $('#campaign-filter').addEventListener('change', renderCampaigns);
  $('#campaigns-refresh').addEventListener('click', () => loadCampaigns().catch(() => {}));
  $('#log-clear').addEventListener('click', () => {
    state.logs = [];
    renderLogs();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && state.token) {
      if (state.tab === 'channels') loadChannels().catch(() => {});
      if (state.tab === 'campaigns') loadCampaigns().catch(() => {});
    }
  });
}

function tokenFromHash() {
  // `api open` launches /#token=... so the dashboard can sign in without the
  // user typing or copying anything. Fragments are not sent to the server.
  const raw = location.hash.startsWith('#') ? location.hash.slice(1) : '';
  if (!raw) return '';
  return new URLSearchParams(raw).get('token') || '';
}

async function init() {
  state.lang = detectLanguage();
  applyTheme(localStorage.getItem(THEME_KEY) || 'dark');
  bindEvents();
  applyLanguage();

  state.authRequired = await checkAuthRequired();
  if (!state.authRequired) {
    try {
      await connect('');
    } catch {
      showGate();
    }
    return;
  }

  const hashToken = tokenFromHash();
  if (hashToken) {
    // Take the token out of the address bar and history before using it.
    history.replaceState(null, '', location.pathname + location.search);
    localStorage.setItem(TOKEN_KEY, hashToken);
    sessionStorage.removeItem(TOKEN_SESSION_KEY);
  }
  const token =
    hashToken ||
    sessionStorage.getItem(TOKEN_SESSION_KEY) ||
    localStorage.getItem(TOKEN_KEY) ||
    '';
  if (!token) {
    showGate();
    return;
  }
  $('#gate-token').value = token;
  try {
    await connect(token);
  } catch {
    state.token = '';
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_SESSION_KEY);
    showGate();
  }
}

document.addEventListener('DOMContentLoaded', init);
