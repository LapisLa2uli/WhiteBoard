const assert = require('assert');
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync('session.py', 'utf8').match(/_METADATA_JS = r"""([\s\S]*?)"""/)[1];

(async () => {
  const calls = [];
  let cancelledBodies = 0;
  const context = vm.createContext({
    window: {}, location: {origin: 'https://school.example'}, URL, AbortController,
    setTimeout, clearTimeout,
    fetch: async (url, options) => {
      calls.push({url, ...options});
      const unsupportedHead = url.endsWith('/fallback') && options.method === 'HEAD';
      const range = options.method === 'GET';
      return {
        url, status: unsupportedHead ? 405 : range ? 206 : 200,
        headers: {get: name => ({'content-type': 'application/pdf', 'content-length': range ? '1' : unsupportedHead ? null : '2048', 'content-range': range ? 'bytes 0-0/2048' : null}[name] || null)},
        body: {cancel: async () => { cancelledBodies++; }},
        text: () => { throw new Error('File body must not be read'); },
      };
    },
  });
  // Reproduce the older Learn page helper that ignores Array.from's mapper.
  vm.runInContext('Array.from = value => new Array(value.length);', context);
  const urls = ['https://school.example/attachments/_1_1/download', 'https://school.example/file', 'https://school.example/fallback', 'https://external.example/file'];
  vm.runInContext(source.replace('__KEY__', '"result"').replace('__URLS__', JSON.stringify(urls)).replace('__LIMIT__', '4'), context);
  for (let tries = 0; !context.window.result && tries < 100; tries++) await new Promise(resolve => setTimeout(resolve, 5));
  const results = context.window.result;
  assert.equal(results.length, 4);
  assert.equal(results[0].status, 206);
  assert.equal(results[1].status, 200);
  assert.equal(results[2].requests, 2);
  assert.equal(results[3].requests, 0);
  assert.equal(calls.length, 4);
  assert.equal(cancelledBodies, 4);
  for (const call of calls) {
    assert.equal(call.mode, 'same-origin');
    assert.equal(call.credentials, 'same-origin');
    if (call.method === 'GET') assert.equal(call.headers.Range, 'bytes=0-0');
  }
  console.log('Metadata regression: legacy Learn helpers, HEAD/range fallback, body cancellation and origins passed.');
})().catch(error => {console.error(error); process.exitCode = 1;});
