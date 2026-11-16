import {Component, createElement, useCallback, useEffect, useRef, useState} from 'react';
import type {ReactNode} from 'react';
import {createRoot} from 'react-dom/client';
import {createApplication, makeEvent, makeResponseEvent, workerEnabled, makeWorkerResponseEvent} from './program.ts';
import type {ApplicationSnapshot, Event} from './program.ts';
import type {Application} from './nex-managed-application.ts';
import {NexError} from './nex-runtime.ts';
import {renderView, currentPath} from './renderer.tsx';
import {RequestRunner, configuredAPIOrigin} from './net.ts';
import {WorkerRunner} from './workers.ts';
import './app.css';
class ErrorBoundary extends Component<{children: ReactNode}, {error: Error | null}> {
  state: {error: Error | null} = {error: null};
  static getDerivedStateFromError(error: Error) { return {error}; }
  render(): ReactNode {
    const error = this.state.error;
    if (!error) return this.props.children;
    const location = error instanceof NexError && error.site ? error.site.join(':') + ': ' : '';
    const code = error instanceof NexError ? error.code + ': ' : '';
    return createElement('main', {role: 'alert'}, createElement('h1', null, 'Application error'), createElement('pre', null, location + code + error.message));
  }
}
function App(): ReactNode {
  const [snapshot, setSnapshot] = useState<ApplicationSnapshot | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);
  const application = useRef<Application<Event, ApplicationSnapshot> | null>(null);
  const runner = useRef<RequestRunner | null>(null), workers = useRef<WorkerRunner | null>(null);
  const live = useRef(false);
  const fail = useCallback((error: unknown) => {
    runner.current?.close(); workers.current?.close(); void application.current?.close();
    if (live.current) setFailure(previous => previous ?? (error instanceof Error ? error : new Error('Application update failed')));
  }, []);
  const publish = useCallback((value: ApplicationSnapshot) => {
    if (!live.current) return;
    runner.current?.validate(value.commands); workers.current?.validate(value.worker_commands);
    document.title = value.title; setSnapshot(value);
    runner.current?.run(value.commands); workers.current?.run(value.worker_commands);
  }, []);
  const dispatch = useCallback((event: Event) => {
    const owner = application.current;
    if (!owner || !live.current) return;
    void owner.dispatch(event).then(value => {
      if (application.current === owner && live.current) publish(value);
    }).catch(fail);
  }, [publish, fail]);
  useEffect(() => {
    live.current = true;
    const owner = createApplication(); application.current = owner;
    const route = () => dispatch(makeEvent('route', '', currentPath()));
    try {
      runner.current = new RequestRunner((action, id, status, body, code, message) => {
        try { dispatch(makeResponseEvent(action, id, status, body, code, message, currentPath())); }
        catch (error) { fail(error); }
      }, window.location.href, globalThis.fetch.bind(globalThis), configuredAPIOrigin(document));
      if (workerEnabled) workers.current = new WorkerRunner((action, id, body, code, message) => {
        try { dispatch(makeWorkerResponseEvent(action, id, body, code, message, currentPath())); }
        catch (error) { fail(error); }
      });
      void owner.ready.then(value => {
        if (application.current === owner && live.current) { publish(value); route(); }
      }).catch(fail);
      window.addEventListener('popstate', route); window.addEventListener('hashchange', route);
    } catch (error) { fail(error); }
    return () => {
      live.current = false; runner.current?.close(); workers.current?.close(); runner.current = null; workers.current = null;
      if (application.current === owner) application.current = null;
      void owner.close();
      window.removeEventListener('popstate', route); window.removeEventListener('hashchange', route);
    };
  }, [dispatch, publish, fail]);
  if (failure) throw failure;
  if (!snapshot) return createElement('main', {role: 'status'}, 'Loading…');
  return renderView(snapshot.view, dispatch);
}
const root = document.getElementById('root');
if (!root) throw new NexError('E_UI', 'Missing root element');
createRoot(root).render(createElement(ErrorBoundary, null, createElement(App)));
