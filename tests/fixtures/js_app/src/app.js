// Imports a local util (resolved) and react (external, unresolved internally).
import { greet } from './lib/util';
import React from 'react';

export function App() {
  return greet('world');
}
