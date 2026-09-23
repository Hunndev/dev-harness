const { value } = require('./value');
describe('Behavior', () => { test('returns value', async () => { await Promise.resolve(); expect(value()).toBe(2); }); });
