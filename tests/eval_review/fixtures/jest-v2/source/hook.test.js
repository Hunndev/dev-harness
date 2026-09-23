const { value } = require('./value');
describe('Behavior', () => {
  beforeEach(() => { expect(value()).toBe(2); });
  test('returns value', () => { expect(true).toBe(true); });
});
