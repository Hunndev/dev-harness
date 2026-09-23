const { value } = require('./value');
describe('Behavior', () => {
  beforeEach(async () => { await Promise.resolve(); expect(value()).toBe(2); });
  test('returns value', () => { expect(true).toBe(true); });
});
