// Offline test: reads mocked Drive JSON, never mutates the queue.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '..', 'integrations', 'google-apps-script', 'Code.gs'), 'utf8');

function file(name, text) {
  return {
    getName: () => name,
    getSize: () => text.length,
    getBlob: () => ({getDataAsString: () => text}),
    getUrl: () => 'https://drive.google.com/file/d/fixture',
  };
}
function folder(children = {}, items = []) {
  return {
    getFoldersByName: name => {
      const match = children[name];
      let used = false;
      return {hasNext: () => !!match && !used, next: () => {used = true; return match;}};
    },
    getFiles: () => {
      let i = 0;
      return {hasNext: () => i < items.length, next: () => items[i++]};
    }
  };
}
function job(id, time, status) {
  return file(id + '.json', JSON.stringify({
    job_id: id, project_title: '사석', shot_id: 'S1', scene_id: 1,
    stage: 'test', progress: status === 'done' ? 100 : 10,
    updated_at: time, output: {result_file: 'outputs/shots/' + id + '.mp4'}
  }));
}
function harness(root) {
  const state = {writes: [], clears: 0, released: false};
  const sheet = {
    getLastRow: () => 1,
    getRange: (r, c, h, w) => ({
      getValues: () => [Array(w).fill('')],
      setValues: values => {state.writes.push({r, values}); return {setFontWeight: () => {}};},
      clearContent: () => {state.clears += 1;}
    }),
    setFrozenRows: () => {}
  };
  const sandbox = {
    SpreadsheetApp: {getActiveSpreadsheet: () => ({
      getSheetByName: () => sheet, insertSheet: () => sheet
    })},
    PropertiesService: {getScriptProperties: () => ({
      getProperty: key => key === 'SASEOK_QUEUE_FOLDER_ID' ? 'queue-id' : null
    })},
    DriveApp: {getFolderById: id => {assert.equal(id, 'queue-id'); return root;}},
    LockService: {getScriptLock: () => ({
      tryLock: () => true, releaseLock: () => {state.released = true;}
    })},
    console
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return {sandbox, state};
}

const old = job('job_1', '2026-01-01T01:00:00Z', 'queued');
const fresh = job('job_1', '2026-01-01T02:00:00Z', 'done');
const done2 = job('job_2', '2026-01-01T03:00:00Z', 'done');
const root = folder({jobs: folder({
  queued: folder({}, [old]), done: folder({}, [fresh, done2])
})});
const success = harness(root);
assert.equal(success.sandbox.syncJobDashboard().jobs, 2);
assert.equal(success.state.writes.length, 2); // header + data
assert.equal(success.state.writes[1].values[0][0], 'job_2');
assert.equal(success.state.writes[1].values[1][4], 'done');
assert.equal(success.state.released, true);

const broken = harness(folder({jobs: folder({running: folder({}, [file('bad.json', '{')])})}));
assert.throws(() => broken.sandbox.syncJobDashboard(), /JSON 파싱 실패/);
assert.equal(broken.state.writes.length, 0);
assert.equal(broken.state.clears, 0);
assert.equal(broken.state.released, true);

const huge = harness(folder({jobs: folder({done: folder({}, [file('large.json', 'x'.repeat(102401))])})}));
assert.throws(() => huge.sandbox.syncJobDashboard(), /크기 초과/);
assert.equal(huge.state.writes.length, 0);

const formula = harness(folder({jobs: folder({done: folder({}, [file('f.json', JSON.stringify({
  job_id: 'job_3', project_title: '=HYPERLINK("bad")',
  updated_at: '2026-01-01T04:00:00Z'
}))])})}));
formula.sandbox.syncJobDashboard();
assert.match(formula.state.writes[1].values[0][1], /^'/);
console.log('SASEOK GAS dashboard tests passed');
