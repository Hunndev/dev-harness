const { value } = require('./value');
function h(n) { if (n === 0) { expect(value()).toBe(2); return; } h(n - 1); }
describe('Behavior', () => { test('returns value', () => { h(12); }); });
