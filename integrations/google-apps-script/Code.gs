/**
 * SASEOK GPU Queue: read-only Drive JSON -> spreadsheet job dashboard.
 * The Colab worker remains the only authority that modifies job JSON files.
 */
const SASEOK_TAB = '렌더작업';
const SASEOK_STATES = ['queued', 'running', 'done', 'failed', 'cancelled'];
const SASEOK_COLUMNS = [
  '작업 ID', '프로젝트', '장면', '컷', '상태', '단계',
  '진행률(%)', '최종 갱신', '결과 경로', '오류', 'Drive JSON'
];
const SASEOK_MAX_FILES = 500;
const SASEOK_MAX_JSON_BYTES = 102400;

function onOpen() {
  SpreadsheetApp.getUi().createMenu('사석 렌더 현황')
    .addItem('작업 현황 새로고침', 'syncJobDashboardFromMenu')
    .addItem('1시간마다 자동 새로고침 설정', 'installHourlyJobSync')
    .addItem('자동 새로고침 중지', 'removeHourlyJobSync')
    .addToUi();
}

function saseokSingleFolder_(parent, name, required) {
  const found = parent.getFoldersByName(name);
  if (!found.hasNext()) {
    if (required) throw new Error(name + ' 폴더가 없습니다.');
    return null;
  }
  const folder = found.next();
  if (found.hasNext()) throw new Error('동일한 이름의 폴더가 여러 개입니다: ' + name);
  return folder;
}

function saseokSafeText_(value) {
  const text = value == null ? '' : String(value);
  // Spreadsheet setValues parses leading '=' as formulas: never execute job text.
  return text.charAt(0) === '=' ? "'" + text : text;
}

function saseokJobRow_(json, state, file) {
  if (!json || typeof json !== 'object' || !json.job_id ||
      !/^[a-zA-Z0-9_.-]+$/.test(String(json.job_id))) {
    throw new Error('올바르지 않은 job_id: ' + file.getName());
  }
  const output = json.output || {};
  const progress = Number(json.progress);
  return [
    saseokSafeText_(json.job_id),
    saseokSafeText_(json.project_title),
    saseokSafeText_(json.scene_id),
    saseokSafeText_(json.shot_id),
    state,
    saseokSafeText_(json.stage),
    Number.isFinite(progress) ? Math.max(0, Math.min(100, progress)) : 0,
    saseokSafeText_(json.updated_at),
    saseokSafeText_(output.result_file),
    saseokSafeText_(json.error),
    file.getUrl()
  ];
}

function saseokCollectRows_(queueRoot) {
  const jobs = saseokSingleFolder_(queueRoot, 'jobs', true);
  const byId = new Map();
  let count = 0;
  SASEOK_STATES.forEach((state, stateIndex) => {
    const folder = saseokSingleFolder_(jobs, state, false);
    if (!folder) return;
    const files = folder.getFiles();
    while (files.hasNext()) {
      const file = files.next();
      if (!file.getName().endsWith('.json')) continue;
      count += 1;
      if (count > SASEOK_MAX_FILES) {
        throw new Error('JSON 파일이 ' + SASEOK_MAX_FILES + '개를 초과했습니다. 기존 시트는 유지합니다.');
      }
      if (file.getSize() > SASEOK_MAX_JSON_BYTES) {
        throw new Error('JSON 파일 크기 초과: ' + file.getName());
      }
      let data;
      try {
        data = JSON.parse(file.getBlob().getDataAsString('UTF-8'));
      } catch (error) {
        throw new Error('JSON 파싱 실패 (' + file.getName() + '): ' + error.message);
      }
      const row = saseokJobRow_(data, state, file);
      const jobId = row[0];
      const existing = byId.get(jobId);
      // During Drive syncing the same job may briefly appear in two folders.
      // Prefer latest ISO updated_at, then more terminal state for ties.
      if (!existing || row[7] > existing.row[7] ||
          (row[7] === existing.row[7] && stateIndex > existing.stateIndex)) {
        byId.set(jobId, {row: row, stateIndex: stateIndex});
      }
    }
  });
  return Array.from(byId.values()).map(item => item.row)
    .sort((a, b) => String(b[7]).localeCompare(String(a[7])));
}

function saseokDashboardSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SASEOK_TAB) || ss.insertSheet(SASEOK_TAB);
  const header = sheet.getRange(1, 1, 1, SASEOK_COLUMNS.length);
  const old = header.getValues()[0];
  if (old.some(v => String(v).trim()) &&
      SASEOK_COLUMNS.some((v, index) => old[index] !== v)) {
    throw new Error('기존 렌더작업 탭의 열 구조가 다릅니다. 덮어쓰지 않습니다.');
  }
  header.setValues([SASEOK_COLUMNS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  return sheet;
}

function syncJobDashboard() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) throw new Error('다른 현황 동기화가 진행 중입니다.');
  try {
    const folderId = PropertiesService.getScriptProperties()
      .getProperty('SASEOK_QUEUE_FOLDER_ID');
    if (!folderId) throw new Error('Script Properties에 SASEOK_QUEUE_FOLDER_ID가 필요합니다.');
    const queueRoot = DriveApp.getFolderById(folderId);
    const rows = saseokCollectRows_(queueRoot); // Must succeed before touching sheet.
    const sheet = saseokDashboardSheet_();
    const previous = Math.max(0, sheet.getLastRow() - 1);
    if (previous > 0) {
      sheet.getRange(2, 1, previous, SASEOK_COLUMNS.length).clearContent();
    }
    if (rows.length) {
      sheet.getRange(2, 1, rows.length, SASEOK_COLUMNS.length).setValues(rows);
    }
    const result = {jobs: rows.length, refreshed_at: new Date().toISOString()};
    console.log('SASEOK Drive dashboard refreshed: ' + rows.length);
    return result;
  } finally {
    lock.releaseLock();
  }
}

function syncJobDashboardFromMenu() {
  const result = syncJobDashboard();
  SpreadsheetApp.getUi().alert(result.jobs + '개 작업을 시트에 표시했습니다.');
}

function installHourlyJobSync() {
  removeHourlyJobSync();
  ScriptApp.newTrigger('syncJobDashboard').timeBased().everyHours(1).create();
  SpreadsheetApp.getUi().alert('1시간마다 작업 현황을 새로고침하도록 설정했습니다.');
}

function removeHourlyJobSync() {
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === 'syncJobDashboard') {
      ScriptApp.deleteTrigger(trigger);
    }
  });
}
