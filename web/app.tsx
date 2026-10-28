import { Component, createElement, useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { initial, update, view, title, commands, makeEvent, makeResponseEvent } from './program.ts';
import type { Event } from './program.ts';
import { NexError } from './nex-runtime.ts';
import { renderView, currentPath } from './renderer.tsx';
import { RequestRunner, configuredAPIOrigin } from './net.ts';
import './app.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render(): ReactNode {
    const error = this.state.error;
    if (!error) return this.props.children;
    const location = error instanceof NexError && error.site ? error.site.join(':') + ': ' : '';
    const code = error instanceof NexError ? error.code + ': ' : '';
    return createElement('main', { role: 'alert' }, createElement('h1', null, 'Application error'), createElement('pre', null, location + code + error.message));
  }
}
function App(): ReactNode {
  const [state, setState] = useState(initial);
  const [failure, setFailure] = useState<Error | null>(null);
  const current = useRef(state), runner = useRef<RequestRunner | null>(null);
  const events = useRef<Event[]>([]), processing = useRef(false);
  const dispatch = useCallback((event: Event) => {
    events.current.push(event);
    if (processing.current) return;
    processing.current = true;
    try {
      while (events.current.length) {
        const input = events.current.shift()!;
        const before = current.current, after = update(before, input);
        const work = commands(before, after, input);
        current.current = after; setState(after);
        runner.current?.run(work);
      }
    } catch (error) {
      runner.current?.close(); events.current = [];
      setFailure(error instanceof Error ? error : new Error('Application update failed'));
    } finally { processing.current = false; }
  }, []);
  useEffect(() => {
    try { runner.current = new RequestRunner((action, id, status, body, code, message) => {
      try { dispatch(makeResponseEvent(action, id, status, body, code, message, currentPath())); }
      catch (error) { runner.current?.close(); setFailure(error instanceof Error ? error : new Error('Invalid response event')); }
    }, window.location.href, globalThis.fetch.bind(globalThis), configuredAPIOrigin(document));
    } catch (error) { setFailure(error instanceof Error ? error : new Error('Invalid host configuration')); return; }
    document.title = title();
    const route = () => dispatch(makeEvent('route', '', currentPath()));
    route(); window.addEventListener('popstate', route); window.addEventListener('hashchange', route);
    return () => { runner.current?.close(); runner.current = null; window.removeEventListener('popstate', route); window.removeEventListener('hashchange', route); };
  }, [dispatch]);
  if (failure) throw failure;
  return renderView(view(state), dispatch);
}
const root = document.getElementById('root');
if (!root) throw new NexError('E_UI', 'Missing root element');
createRoot(root).render(createElement(ErrorBoundary, null, createElement(App)));
