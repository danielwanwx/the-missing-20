const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { BarcodeFormat } = require('@zxing/library');

function setup(overrides = {}) {
  const timers = [];
  let stopped = 0;
  const stream = { getTracks: () => [{ stop: () => stopped++ }] };
  const video = { pause() {}, removeAttribute() {}, play: async () => {}, readyState: 2, videoWidth: 640, videoHeight: 480 };
  const context = { module: { exports: {} }, URL: { createObjectURL: () => 'blob:local', revokeObjectURL() {} },
    navigator: { mediaDevices: { getUserMedia: async () => stream } },
    document: { createElement: () => ({ getContext: () => ({ drawImage() {}, translate() {}, rotate() {} }) }) },
    setTimeout: (cb) => { timers.push(cb); return timers.length; }, clearTimeout() {}, ...overrides };
  vm.runInNewContext(fs.readFileSync('workspace/barcode-capture.js', 'utf8'), context);
  return { ...context.module.exports, context, video, stream, timers, stopped: () => stopped };
}

test('fallback format mapping follows pinned decoder enum, including QR and UPC', async () => {
  for (const [format, expected] of [[BarcodeFormat.UPC_A, 'upc_a'], [BarcodeFormat.QR_CODE, 'qr_code'], [BarcodeFormat.EAN_13, 'ean_13'], [BarcodeFormat.CODE_128, 'code_128']]) {
    const env = setup({ ZXingBrowser: { BrowserMultiFormatReader: class {
      decodeFromCanvas() { return { getBarcodeFormat: () => format, getText: () => '036000291452' }; }
    } } });
    assert.equal((await (await env.decoder())({}))[0].format, expected);
  }
});

test('native runtime failure uses the bundled fallback', async () => {
  class Broken { static async getSupportedFormats() { return ['ean_13', 'upc_a', 'qr_code', 'code_128']; } async detect() { throw Error('native unavailable'); } }
  const env = setup({ BarcodeDetector: Broken, ZXingBrowser: { BrowserMultiFormatReader: class {
    decodeFromCanvas() { return { getBarcodeFormat: () => BarcodeFormat.QR_CODE, getText: () => 'box-01' }; }
  } } });
  assert.equal((await (await env.decoder())({}))[0].rawValue, 'box-01');
});

test('minified decoder no-code exceptions do not terminate scanning', async () => {
  const env = setup({ ZXingBrowser: { BrowserMultiFormatReader: class {
    decodeFromCanvas() { const error = Error('no code'); error.name = 'e'; error.getKind = () => 'NotFoundException'; throw error; }
  } } });
  assert.equal((await (await env.decoder())({})).length, 0);
});

test('different orientation readings cannot identify goods from a glare-corrupted code', async () => {
  let reads = 0;
  const env = setup({ ZXingBrowser: { BrowserMultiFormatReader: class {
    decodeFromCanvas() { return { getBarcodeFormat: () => BarcodeFormat.UPC_A, getText: () => ++reads === 1 ? '070097026788' : '070097025088' }; }
  } } });
  await assert.rejects((await env.decoder())({ width: 512, height: 384 }), /Conflicting barcode readings/);
});

test('native one-dimensional identity must agree with fallback verification', async () => {
  class Native { static async getSupportedFormats() { return ['ean_13', 'upc_a', 'qr_code', 'code_128']; } async detect() { return [{rawValue:'070097026788',format:'upc_a'}]; } }
  const env = setup({ BarcodeDetector: Native, ZXingBrowser: { BrowserMultiFormatReader: class {
    decodeFromCanvas() { return { getBarcodeFormat: () => BarcodeFormat.UPC_A, getText: () => '070097025088' }; }
  } } });
  await assert.rejects((await env.decoder())({}), /Conflicting barcode readings/);
});

test('one transient decoded frame is not handed to the receiving workflow', async () => {
  const env = setup(); const codes = []; let frame = 0;
  const capture = new env.BarcodeCapture({ video: env.video, onState() {}, onCode: async code => codes.push(code),
    makeDecoder: async () => async () => ++frame === 1 ? [{rawValue:'wrong-unit',format:'qr_code'}] : [{rawValue:'right-unit',format:'qr_code'}] });
  await capture.start(); assert.deepEqual(codes, []);
  await env.timers.shift()(); assert.deepEqual(codes, []);
  await env.timers.shift()(); assert.deepEqual(codes, ['right-unit']);
  capture.stop();
});

test('duplicate video frames invoke the business boundary once; stop releases camera', async () => {
  const env = setup(); const codes = [];
  const capture = new env.BarcodeCapture({ video: env.video, onState() {}, onCode: async (code) => codes.push(code),
    makeDecoder: async () => async () => [{ rawValue: 'box-01', format: 'qr_code' }] });
  await capture.start(); await env.timers.shift()();
  assert.deepEqual(codes, ['box-01']);
  capture.stop(); assert.equal(env.stopped(), 1);
  await env.timers.shift()(); assert.deepEqual(codes, ['box-01']);
});

test('closing while permission is pending releases the late stream without decoding', async () => {
  const env = setup(); let grant; let called = 0;
  env.context.navigator.mediaDevices.getUserMedia = () => new Promise((resolve) => { grant = resolve; });
  const capture = new env.BarcodeCapture({ video: env.video, onState() {}, onCode() { called++; }, makeDecoder: async () => async () => [] });
  const pending = capture.start(); await new Promise(setImmediate);
  capture.stop(); grant(env.stream); await pending;
  assert.equal(env.stopped(), 1); assert.equal(called, 0); assert.equal(env.timers.length, 0);
});

test('unsupported or oversized video does not open the camera', async () => {
  const env = setup(); const states = [];
  const capture = new env.BarcodeCapture({ video: env.video, onState: (state) => states.push(state), onCode() {}, makeDecoder: async () => assert.fail() });
  await capture.start({ type: 'text/plain', size: 1 });
  assert.match(states.at(-1), /video smaller/);
});
