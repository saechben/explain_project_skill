// Imports a module that does not exist (unresolved internal import).
import { missing } from './does-not-exist';

export function greet(name) {
  return 'hello ' + name + missing;
}
