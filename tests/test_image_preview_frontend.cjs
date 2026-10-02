const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const page = fs.readFileSync(0, 'utf8');
const script = page.match(/<script>([\s\S]*?)<\/script>/)[1];

async function checkSubmission(mode) {
  const elements = new Map();
  const events = new Map();
  const requests = [];
  let closeAttempts = 0;
  const element = id => {
    if (!elements.has(id)) {
      elements.set(id, {
        style: {}, disabled: false, value: ' Reviewed ', checked: true, scrollHeight: 20,
        addEventListener: (type, callback) => events.set(`${id}:${type}`, callback),
      });
    }
    return elements.get(id);
  };
  const fields = [element('name'), element('include'), element('image-wrap')];
  const card = {dataset: {id: '1'}, querySelector: selector => element(selector.slice(1))};
  const document = {
    title: '',
    getElementById: element,
    querySelectorAll: selector => {
      if (selector === '.card') return [card];
      if (selector === 'textarea') return [element('name')];
      if (selector === 'textarea, input, .image-wrap') return fields;
      return [];
    },
  };
  const context = vm.createContext({
    document,
    window: {close: () => {
      closeAttempts += 1;
      if (mode === 'close-throws') throw new Error('Closing is restricted');
    }},
    fetch: async (url, options) => {
      requests.push({url, options});
      if (mode === 'network-error') throw new Error('Network unavailable');
      return {
        ok: mode !== 'http-error',
        json: async () => ({ok: mode !== 'rejected', error: 'Not accepted'}),
      };
    },
  });
  vm.runInContext(script, context);
  await events.get('confirm:click')();

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, '/confirm');
  assert.equal(requests[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(requests[0].options.body), [{id: '1', name: 'Reviewed', include: true}]);
  const accepted = mode === 'close-blocked' || mode === 'close-throws';
  assert.equal(closeAttempts, accepted ? 1 : 0);
  assert.equal(element('confirm').disabled, accepted);
  if (accepted) {
    assert.equal(element('confirm').textContent, '已提交');
    assert.match(document.title, /审核已提交/);
    assert.match(element('status').textContent, /此页面可以关闭/);
    assert.ok(fields.every(field => field.disabled));
    assert.doesNotMatch(element('status').textContent, /正在/);
  } else {
    assert.match(element('status').textContent, /提交失败/);
    assert.ok(fields.every(field => !field.disabled));
  }
}

(async () => {
  for (const mode of ['close-blocked', 'close-throws', 'http-error', 'rejected', 'network-error']) {
    await checkSubmission(mode);
  }
  process.stdout.write('Preview submission checks passed: 5 scenarios\n');
})().catch(error => {
  process.stderr.write(error.stack + '\n');
  process.exitCode = 1;
});
